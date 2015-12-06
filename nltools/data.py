'''
    NeuroLearn Data Classes
    =========================
    Classes to represent various types of fdata

    Author: Luke Chang
    License: MIT
'''

## Notes:
# Might consider moving anatomical field out of object and just request when needed.  Probably only when plotting
# Need to figure out how to speed up loading and resampling of data

__all__ = ['Brain_Data']

import os
import nibabel as nib
from nltools.utils import get_resource_path, set_algorithm
from nltools.cross_validation import set_cv
from nltools.plotting import dist_from_hyperplane_plot, scatterplot, probability_plot, roc_plot
from nilearn.input_data import NiftiMasker
from copy import deepcopy
import pandas as pd
import numpy as np
from nilearn.plotting.img_plotting import plot_epi, plot_roi, plot_stat_map
from scipy.stats import ttest_1samp
from scipy.stats import t

import sklearn
from sklearn.pipeline import Pipeline
from nilearn.input_data import NiftiMasker

class Brain_Data(object):

    def __init__(self, data=None, Y=None, X=None, mask=None, output_file=None, anatomical=None, **kwargs):
        """ Initialize Brain_Data Instance.

        Args:
            data: nibabel data instance or list of files
            Y: vector of training labels
            X: Pandas DataFrame Design Matrix for running univariate models 
            mask: binary nifiti file to mask brain data
            output_file: Name to write out to nifti file
            anatomical: anatomical image to overlay plots
            **kwargs: Additional keyword arguments to pass to the prediction algorithm

        """

        if mask is not None:
            if not isinstance(mask, nib.Nifti1Image):
                raise ValueError("mask is not a nibabel instance")
            self.mask = mask
        else:
            self.mask = nib.load(os.path.join(get_resource_path(),'MNI152_T1_2mm_brain_mask.nii.gz'))

        if anatomical is not None:
            if not isinstance(anatomical, nib.Nifti1Image):
                raise ValueError("anatomical is not a nibabel instance")
            self.anatomical = anatomical
        else:
            self.anatomical = nib.load(os.path.join(get_resource_path(),'MNI152_T1_2mm.nii.gz'))

        if type(data) is str:
            data=nib.load(data)
        elif type(data) is list:
            data=nib.concat_images(data)
        elif not isinstance(data, nib.Nifti1Image):
            raise ValueError("data is not a nibabel instance")

        self.nifti_masker = NiftiMasker(mask_img=mask)
        self.data = self.nifti_masker.fit_transform(data)

        if Y is not None:
            if type(Y) is str:
                if os.path.isfile(Y):
                    Y=np.array(pd.read_csv(Y,header=None,index_col=None))
            elif type(Y) is list:
                Y=np.array(Y)
            if self.data.shape[0]!= len(Y):
                raise ValueError("Y does not match the correct size of data")
            if 1 in Y.shape:
                self.Y = np.array(Y).flatten()
            else:
                self.Y = Y
        else:
            self.Y = []

        if X is not None:
            if self.data.shape[0]!= X.shape[0]:
                raise ValueError("X does not match the correct size of data")
            self.X = X
        else:
            self.X = pd.DataFrame()

        if output_file is not None:
            self.file_name = output_file
        else:
            self.file_name = []

    def __repr__(self):
        return '%s.%s(data=%s, Y=%s, X=%s, mask=%s, output_file=%s, anatomical=%s)' % (
            self.__class__.__module__,
            self.__class__.__name__,
            self.shape(),
            self.Y.shape,
            self.X.shape,
            os.path.basename(self.mask.get_filename()),
            self.file_name,
            os.path.basename(self.anatomical.get_filename())            
            )

    def __getitem__(self, index):
        new = deepcopy(self)
        if isinstance(index, int):
            new.data = np.array(self.data[index,:]).flatten()
        elif isinstance(index, slice):
            new.data = np.array(self.data[index,:])            
        else:
            raise TypeError("index must be int or slice")
        if self.Y.size:
            new.Y = self.Y[index]
        if self.X.size:
            if isinstance(self.X,pd.DataFrame):
                new.X = self.X[index]
            else:
                new.X = self.X[:,index]
        return new

    def shape(self):
        """ Get images by voxels shape.

        Args:
            self: Brain_Data instance

        """

        return self.data.shape

    def mean(self):
        """ Get mean of each voxel across images.

        Args:
            self: Brain_Data instance

        Returns:
            out: Brain_Data instance
        
        """ 

        out = deepcopy(self)
        out.data = np.mean(out.data, axis=0)
        return out

    def std(self):
        """ Get standard deviation of each voxel across images.

        Args:
            self: Brain_Data instance

        Returns:
            out: Brain_Data instance
        
        """ 

        out = deepcopy(self)
        out.data = np.std(out.data, axis=0)
        return out

    def to_nifti(self):
        """ Convert Brain_Data Instance into Nifti Object

        Args:
            self: Brain_Data instance
        
        """
        
        nifti_dat = self.nifti_masker.inverse_transform(self.data)
        return nifti_dat

    def write(self, file_name=None):
        """ Write out Brain_Data object to Nifti File.

        Args:
            self: Brain_Data instance
            file_name: name of nifti file

        """

        self.to_nifti().to_filename(file_name)

    def plot(self, limit=5):
        """ Create a quick plot of self.data.  Will plot each image separately

        Args:
            self: Brain_Data instance
            limit: max number of images to return
            mask: Binary nifti mask to calculate mean

        """

        if self.data.ndim == 1:
            plot_roi(self.to_nifti(), self.anatomical)
        else:
            for i in xrange(self.data.shape[0]):
                if i < limit:
                    plot_roi(self.nifti_masker.inverse_transform(self.data[i,:]), self.anatomical)


    def regress(self):
        """ run vectorized OLS regression across voxels.

        Args:
            self: Brain_Data instance

        Returns:
            out: dictionary of regression statistics in Brain_Data instances {'beta','t','p','df','residual'}
        
        """ 

        if not isinstance(self.X, pd.DataFrame):
            raise ValueError('Make sure self.X is a pandas DataFrame.')

        if self.X.empty:
            raise ValueError('Make sure self.X is not empty.')

        if self.data.shape[0]!= self.X.shape[0]:
            raise ValueError("self.X does not match the correct size of self.data")

        b = np.dot(np.linalg.pinv(self.X), self.data)
        res = self.data - np.dot(self.X,b)
        sigma = np.std(res,axis=0)
        stderr = np.dot(np.matrix(np.diagonal(np.linalg.inv(np.dot(self.X.T,self.X)))**.5).T,np.matrix(sigma))
        b_out = deepcopy(self)
        b_out.data = b
        t_out = deepcopy(self)
        t_out.data = b /stderr
        df = np.array([self.X.shape[0]-self.X.shape[1]] * t_out.data.shape[1])
        p_out = deepcopy(self)
        p_out.data = 2*(1-t.cdf(np.abs(t_out.data),df))

 
        # Might want to not output this info
        df_out = deepcopy(self)
        df_out.data = df
        sigma_out = deepcopy(self)
        sigma_out.data = sigma
        res_out = deepcopy(self)
        res_out.data = res

        return {'beta':b_out, 't':t_out, 'p':p_out, 'df':df_out, 'sigma':sigma_out, 'residual':res_out}

    def ttest(self, threshold_dict=None):
        """ Calculate one sample t-test across each voxel (two-sided)

        Args:
            self: Brain_Data instance
            threshold_dict: a dictionary of threshold parameters {'unc':.001} or {'fdr':.05}

        Returns:
            out: dictionary of regression statistics in Brain_Data instances {'t','p'}
        
        """ 

        # Notes:  Need to add FDR Option

        t = deepcopy(self)
        p = deepcopy(self)
        t.data, p.data = ttest_1samp(self.data, 0, 0)

        if threshold_dict is not None:
            if type(threshold_dict) is dict:
                if 'unc' in threshold_dict:
                    #Uncorrected Thresholding
                    t.data[np.where(p.data>threshold_dict['unc'])] = np.nan
                elif 'fdr' in threshold_dict:
                    pass
            else:
                raise ValueError("threshold_dict is not a dictionary.  Make sure it is in the form of {'unc':.001} or {'fdr':.05}")

        out = {'t':t, 'p':p}

        return out

    def append(self, data):
        """ Append data to Brain_Data instance

        Args:
            data: Brain_Data instance to append
        
        """

        if not isinstance(data, Brain_Data):
            raise ValueError('Make sure data is a Brain_Data instance')
 
        out = deepcopy(self)

        if out.isempty():
            out.data = data.data            
        else:
            if len(self.shape())==1 & len(data.shape())==1:
                if self.shape()[0]!=data.shape()[0]:
                    raise ValueError('Data is a different number of voxels then the weight_map.')
            elif len(self.shape())==1 & len(data.shape())>1:
                if self.shape()[0]!=data.shape()[1]:
                    raise ValueError('Data is a different number of voxels then the weight_map.')
            elif len(self.shape())>1 & len(data.shape())==1:
                if self.shape()[1]!=data.shape()[0]:
                    raise ValueError('Data is a different number of voxels then the weight_map.')
            elif self.shape()[1]!=data.shape()[1]:
                raise ValueError('Data is a different number of voxels then the weight_map.')

            out.data = np.vstack([self.data,data.data])

        return out

    def empty(self, data=True, Y=True, X=True):
        """ Initalize Brain_Data.data as empty
        
        """
        
        tmp = deepcopy(self)
        if data:
            tmp.data = np.array([])
        if Y:
            tmp.Y = np.array([])
        if X:
            tmp.X = np.array([])
        # tmp.data = np.array([]).reshape(0,n_voxels)
        return tmp

    def isempty(self):
        """ Check if Brain_Data.data is empty
        
        Returns:
            bool
        """ 

        if isinstance(self.data,np.ndarray):
            if self.data.size:
                boolean = False
            else:
                boolean = True

        if isinstance(self.data, list):
            if not self.data:
                boolean = True
            else:
                boolean = False
        
        return boolean

    def similarity(self, image=None, method='correlation', ignore_missing=True):
        """ Calculate similarity of Brain_Data() instance with single Brain_Data image

            Args:
                self: Brain_Data instance of data to be applied
                weight_map: Brain_Data instance of weight map
                **kwargs: Additional parameters to pass

            Returns:
                pexp: Outputs a vector of pattern expression values

        """

        if not isinstance(self, Brain_Data):
            raise ValueError('Make sure data is a Brain_Data instance')

        if not isinstance(image, Brain_Data):
            raise ValueError('Make sure image is a Brain_Data instance')

        if self.shape()[1]!=image.shape()[0]:
            print 'Warning: Different number of voxels detected.  Resampling image into data space.'

            # raise ValueError('Data is a different number of voxels then the image.')

        # Calculate pattern expression
        if method is 'dot_product':
            pexp = np.dot(self.data, image.data)
        elif method is 'correlation':
            pexp=[]
            for w in xrange(self.data.shape[0]):
                pexp.append(pearson(self.data[w,:], image.data))
            pexp = np.array(pexp).flatten()
        return pexp

    def resample(self, target):
        """ Resample data into target space

        Args:
            self: Brain_Data instance
            target: Brain_Data instance of target space
        
        """ 

        if not isinstance(target, Brain_Data):
            raise ValueError('Make sure target is a Brain_Data instance')
 
        pass

    def predict(self, algorithm=None, cv_dict=None, plot=True, **kwargs):

        """ Run prediction

        Args:
            algorithm: Algorithm to use for prediction.  Must be one of 'svm', 'svr',
            'linear', 'logistic', 'lasso', 'ridge', 'ridgeClassifier','randomforest',
            or 'randomforestClassifier'
            cv_dict: Type of cross_validation to use. A dictionary of
                {'type': 'kfolds', 'n_folds': n},
                {'type': 'kfolds', 'n_folds': n, 'subject_id': holdout}, or
                {'type': 'loso'', 'subject_id': holdout},
                where n = number of folds, and subject = vector of subject ids that corresponds to self.Y
            save_images: Boolean indicating whether or not to save images to file.
            save_output: Boolean indicating whether or not to save prediction output to file.
            save_plot: Boolean indicating whether or not to create plots.
            **kwargs: Additional keyword arguments to pass to the prediction algorithm

        Returns:
            output: a dictionary of prediction parameters

        """

        # Set algorithm
        if algorithm is not None:
            predictor_settings = set_algorithm(algorithm, **kwargs)
        else:
            # Use SVR as a default
            predictor_settings = set_algorithm('svr', **{'kernel':"linear"})

        # Initialize output dictionary
        output = {}
        output['Y'] = self.Y

        # Overall Fit for weight map
        predictor = predictor_settings['predictor']
        predictor.fit(self.data, self.Y)
        output['yfit_all'] = predictor.predict(self.data)
        if predictor_settings['prediction_type'] == 'classification':
            if predictor_settings['algorithm'] not in ['svm','ridgeClassifier','ridgeClassifierCV']:
                output['prob_all'] = predictor.predict_proba(self.data)
            else:
                output['dist_from_hyperplane_all'] = predictor.decision_function(self.data)
                if predictor_settings['algorithm'] == 'svm' and predictor.probability:
                    output['prob_all'] = predictor.predict_proba(self.data)
       
        output['intercept'] = predictor.intercept_

        # Weight map
        output['weight_map'] = deepcopy(self)
        if predictor_settings['algorithm'] == 'lassopcr':
            output['weight_map'].data = np.dot(predictor_settings['_pca'].components_.T,predictor_settings['_lasso'].coef_)
        elif predictor_settings['algorithm'] == 'pcr':
            output['weight_map'].data = np.dot(predictor_settings['_pca'].components_.T,predictor_settings['_regress'].coef_)
        else:
            output['weight_map'].data = predictor.coef_.squeeze()

        # Cross-Validation Fit
        if cv_dict is not None:
            cv = set_cv(cv_dict)

            predictor_cv = predictor_settings['predictor']
            output['yfit_xval'] = output['yfit_all'].copy()
            output['intercept_xval'] = []
            output['weight_map_xval'] = deepcopy(output['weight_map'])
            wt_map_xval = [];
            if predictor_settings['prediction_type'] == 'classification':
                if predictor_settings['algorithm'] not in ['svm','ridgeClassifier','ridgeClassifierCV']:
                    output['prob_xval'] = np.zeros(len(self.Y))
                else:
                    dist_from_hyperplane_xval = np.zeros(len(self.Y))
                    if predictor_settings['algorithm'] == 'svm' and predictor_cv.probability:
                        output['prob_xval'] = np.zeros(len(self.Y))

            for train, test in cv:
                predictor_cv.fit(self.data[train], self.Y[train])
                output['yfit_xval'][test] = predictor_cv.predict(self.data[test])
                if predictor_settings['prediction_type'] == 'classification':
                    if predictor_settings['algorithm'] not in ['svm','ridgeClassifier','ridgeClassifierCV']:
                        output['prob_xval'][test] = predictor_cv.predict_proba(self.data[test])
                    else:
                        output['dist_from_hyperplane_xval'][test] = predictor_cv.decision_function(self.data[test])
                        if predictor_settings['algorithm'] == 'svm' and predictor_cv.probability:
                            output['prob_xval'][test] = predictor_cv.predict_proba(self.data[test])
                output['intercept_xval'].append(predictor_cv.intercept_)

                # Weight map
                if predictor_settings['algorithm'] == 'lassopcr':
                    wt_map_xval.append(np.dot(predictor_settings['_pca'].components_.T,predictor_settings['_lasso'].coef_))
                elif predictor_settings['algorithm'] == 'pcr':
                    wt_map_xval.append(np.dot(predictor_settings['_pca'].components_.T,predictor_settings['_regress'].coef_))
                else:
                    wt_map_xval.append(predictor_cv.coef_.squeeze())
                output['weight_map_xval'].data = np.array(wt_map_xval)
        
        # Print Results
        if predictor_settings['prediction_type'] == 'classification':
            output['mcr_all'] = np.mean(output['yfit_all']==self.Y)
            print 'overall accuracy: %.2f' % output['mcr_all']
            if cv_dict is not None:
                output['mcr_xval'] = np.mean(output['yfit_xval']==self.Y)
                print 'overall CV accuracy: %.2f' % output['mcr_xval']
        elif predictor_settings['prediction_type'] == 'prediction':
            output['rmse_all'] = np.sqrt(np.mean((output['yfit_all']-self.Y)**2))
            output['r_all'] = np.corrcoef(self.Y,output['yfit_all'])[0,1]
            print 'overall Root Mean Squared Error: %.2f' % output['rmse_all']
            print 'overall Correlation: %.2f' % output['r_all']
            if cv_dict is not None:
                output['rmse_xval'] = np.sqrt(np.mean((output['yfit_xval']-self.Y)**2))
                output['r_xval'] = np.corrcoef(self.Y,output['yfit_xval'])[0,1]
                print 'overall CV Root Mean Squared Error: %.2f' % output['rmse_xval']
                print 'overall CV Correlation: %.2f' % output['r_xval']

        # Plot
        if plot:
            fig1 = plot_stat_map(output['weight_map'].to_nifti(), self.anatomical, title=predictor_settings['algorithm'] + " weights",
                            cut_coords=range(-40, 40, 10), display_mode='z')
            if predictor_settings['prediction_type'] == 'prediction':
                fig2 = scatterplot(pd.DataFrame({'Y': output['Y'], 'yfit_xval':output['yfit_xval']}))
            elif self.prediction_type == 'classification':
                if self.algorithm not in ['svm','ridgeClassifier','ridgeClassifierCV']:
                    fig2 = probability_plot(pd.DataFrame({'Y': output['Y'], 'Probability_xval':output['prob_xval']})) 
                else:
                    fig2 = dist_from_hyperplane_plot(pd.DataFrame({'Y': output['Y'], 'dist_from_hyperplane_xval':output['dist_from_hyperplane_xval']}))
                    if self.algorithm == 'svm' and self.predictor.probability:
                        fig3 = probability_plot(pd.DataFrame({'Y': output['Y'], 'Probability_xval':output['prob_xval']}))

        return output


