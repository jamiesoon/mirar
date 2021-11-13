import numpy as np
import os
from glob import glob
from astropy.io import fits
import logging
from winterdrp.preprocessing.bias import load_master_bias

logger = logging.getLogger(__name__)

base_mdark_name = "master_dark"

def mdark_name(exptime, norm=False):
    if norm:
        return f"{base_mdark_name}_normed.fits"
    else:
        return f"{base_mdark_name}_{exptime:.0f}s.fits"

def make_master_dark(darklist, xlolim=500, xuplim=3500, ylolim=500, yuplim=3500, cal_dir='cals', make_norm=True):
    
    if len(darklist) > 0:

        logger.info(f'Found {len(darklist)} dark frames')
        
        with fits.open(darklist[0]) as img:
            header = img[0].header
            
        nx = header['NAXIS1']
        ny = header['NAXIS2']
        
        master_bias = load_master_bias(cal_dir, header)
            
        logger.info("Making one 'master_dark' for each exposure time.")

        explist = []

        for dark in darklist:
            img = fits.open(dark)
            data = img[0].data
            header = img[0].header

            explist.append(header['EXPTIME'])

        exps = sorted(list(set(explist)))

        logger.info(f'Found {len(exps)} different exposure times: {exps}')

        darklist = np.array(darklist)

        dark_loop = []

        for exp in exps:

            mask = np.array([x == exp for x in explist])

            dark_loop.append((
                darklist[mask],
                exp,
                "Median stacked dark",
                os.path.join(cal_dir, mdark_name(exp, norm=False))
            ))
            
        # Optionally loop over all darks

        if make_norm:
            logger.info("Making one additional 'master_dark' combining all exposure times.")
            dark_loop.append((
                darklist,
                1.0,
                "Median stacked normalised dark",
                os.path.join(cal_dir, mdark_name(None, norm=True))
            ))
                
        # Loop over each set of darks and create a master_dark
                
        for (cutdarklist, exptime, history, mdark_path) in dark_loop:
                    
            nframes = len(cutdarklist)
            
            darks = np.zeros((ny,nx,len(cutdarklist)))

            for i, dark in enumerate(cutdarklist):

                img = fits.open(dark)
                dark_exptime = img[0].header['EXPTIME']

                logger.debug(f'Reading dark {i+1}/{nframes} with exposure time {dark_exptime}')
                
                darks[:,:,i] = (img[0].data - master_bias) * exptime/dark_exptime

                img.close()

            master_dark = np.nanmedian(darks,axis=2)

            img = fits.open(darklist[0])
            primaryHeader = img[0].header
            img.close()
            procHDU = fits.PrimaryHDU(master_dark)  # Create a new HDU with the processed image data
            procHDU.header = primaryHeader       # Copy over the header from the raw file

            procHDU.header.add_history(history)
            procHDU.header['EXPTIME'] = exptime

            logger.info(f"Saving stacked 'master dark' combining {nframes} exposures to {mdark_path}")

            procHDU.writeto(mdark_path, overwrite=True)
        return 0
      
    else:
        logger.warning("No dark images provided. No master dark created.")
        
def load_master_darks(cal_dir, header=None, use_norm=False):
    
    master_dark_paths = glob(f'{cal_dir}/{base_mdark_name}*.fits')
    
    mdark_norm_path = mdark_name(None, norm=True)
        
    if len(master_dark_paths) == 0:
        
        try:
            nx = header['NAXIS1']
            ny = header['NAXIS2']

            master_darks = np.zeros((ny,nx))
            
            logger.warning("No master dark found. No dark correction will be applied.")
        
        except (TypeError, KeyError) as e:
            err = "No master dark files found, and no header info provided to create a dummy image."
            logger.error(err)
            raise FileNotFoundError(err)
     
    elif use_norm:
        
        with fits.open(mdark_norm_path) as img:
            master_darks = img[0].data
            
    else:
        
        master_darks = dict()
        
        for mdpath in master_dark_paths:
            if mdark_norm_path not in mdpath:
                
                exp = os.path.basename(mdpath).split("_")[-1][:-6]
                
                master_darks[float(exp)] = mdpath
                
    return master_darks

def select_master_dark(all_master_darks, header):
    
    if isinstance(all_master_darks, np.ndarray):
        master_dark = all_master_darks
    
    elif isinstance(all_master_darks, dict):
        exp = header['EXPTIME']
        try:
            master_dark = all_master_darks[float(exp)]
        except KeyError:
            err = f'Unrecognised key {exp}. Available dark exposure times are {all_master_darks.keys()}'
            logger.error(err)
            raise KeyError(err)
    else:
        err = f"Unrecognised Type for all_master_darks ({type(all_master_darks)}). Was expecting 'numpy.ndarray' or 'dict'."
        logger.error(err)
        raise TypeError(err)
    
    return master_dark