#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
/** 
 *  The script implements streaming image analysis part of the closed-loop system between MicroManager 
 *  and CaImAn toolbox (python). Two processes are communicating through named pipes, which are used for 
 *  sending signals that trigger specific processing steps in both environments. Images that are acquired 
 *  during the recording are saved in a multiTIFF file which is in turn read by CaImAn and used for online 
 *  analysis.
 *  
 *  author: Tea Tompos (master's internship project, June 2020)
 */

"""

# %% ********* Importing packages: *********
import caiman as cm
import logging
from pytictoc import TicToc
from caiman.source_extraction.cnmf import params as params
from caiman.source_extraction import cnmf as cnmf
import os
from caiman.paths import caiman_datadir

# %% ********* Creating named pipes for communication with MicroManager: *********
timer = TicToc()
timer.tic()    # start measuring time

sendPipeName = "/tmp/getPipeMMCaImAn.ser"	       # FOR SENDING MESSAGES --> TO MicroManager
receivePipeName = "/tmp/sendPipeMMCaImAn.ser"     # FOR READING MESSAGES --> FROM MicroManager

MMfileDirectory = '/Applications/MicroManager 2.0 gamma/uMresults'
CaimanFileDirectory = caiman_datadir()   # specify where the file is saved 


if os.path.exists(sendPipeName):
   os.remove(sendPipeName)
   os.mkfifo(sendPipeName)
   print ("Removed old write-pipe, created new write-pipe.")
else: 
   os.mkfifo(sendPipeName)
   print ("Write-pipe created sucessfully!")
   
if os.path.exists(receivePipeName):
   os.remove(receivePipeName)
   os.mkfifo(receivePipeName)
   print ("Removed old read-pipe, created new read-pipe.")
else: 
   os.mkfifo(receivePipeName)
   print ("Read-pipe created sucessfully!")
    
timer.toc()
# %% ********* Wait for file name: *********
print("Waiting for file name..")
pipeRead = open(receivePipeName, 'r')                       # open the read pipe
getFileName = pipeRead.readline()[:-1]                      # wait for message

fullFileName = getFileName + '_MMStack_Default.ome.tif'
fileToProcess = os.path.join(CaimanFileDirectory, 'example_movies', getFileName, fullFileName) # join downstream folders

print("File name received: " + fullFileName)
timer.toc()
# %% ********* Defining parameters: *********
print("*** Defining analysis parameters ***")


fps = 40                # ideally it would be calculated by: (frame2-frame1) / totalTime(s)
decayTime = 0.45        # length of a typical transient in seconds
noiseStd = 'mean'       # PSD averaging method for computing noise std
arSystem = 1            # order of the autoregressive system 
expectedNeurons = 1     # number of expected neurons (upper bound), usually None, but we have only one in FOV
patches = None          # if None, the whole FOV is processed, otherwise: specify half-size of patch in pixels
onePhoton = True        # whether to use 1p processing mode
spatDown = 3            # spatial downsampling during initialisation, increase if there is memory problem (default=2)
tempDown = 1            # temporal downsampling during initialisation, increase if there is memory problem (default=2)
backDown = 5            # additional spatial downsampling factor for background (higher values increase the speed, without accuracy loss)
backComponents = 0      # number of background components (rank) if positive, else exact ring model with following settings
#                         gnb= 0: Return background as b and W
#                         gnb=-1: Return full rank background B
#                         gnb<-1: Don't return background
minCorr = 0.85          # minimum value of correlation image for determining a candidate component during greedy_pnr
minPNR = 20             # minimum value of psnr image for determining a candidate component during greedy_pnr
ringSize = 1.5          # radius of ring (*gSig) for computing background during greedy_pnr
minSNR = 1.5            # traces with SNR above this will get accepted
lowestSNR = 0.5         # traces with SNR below will be rejected
spaceThr = 0.9          # space correlation threshold, components with correlation higher than this will get accepted
neuronRadius = (120, 120) # radius of average neurons (in pixels)
neuronBound = (30, 30)  # half-size of bounding box for each neuron, in general 4*gSig+1


# params for OnACID:
spatDown_online = 3     # spatial downsampling factor for faster processing (if > 1)
epochs = 1              # number of times to go over data
expectedNeurons_online = 1  # number of expected components (for memory allocation purposes)
initFrames = 300        # length of mini batch used for initialization
initMethod_online = 'bare'  # or use 'cnmf'
minSNR_online = 1     # traces with SNR above this will get accepted
motCorrection = False   # flag for motion correction during online analysis
normalize_online = True     # whether to normalize each frame prior to online processing
cnnFlag = True              # whether to use the online CNN classifier for screening candidate components (otherwise space correlation is used)
thresh_CNN_noisy = 0.5      # threshold for the online CNN classifier

# create a dictionary with parameter-value pairs
initialParamsDict = { 'fnames': fileToProcess,
              'fr': fps,
              'decay_time': decayTime,
              'noise_method': noiseStd,
              'p': arSystem,
              'K': expectedNeurons,
              'rf': patches,
              'center_psf': onePhoton,
              'ssub': spatDown,
              'tsub': tempDown,
              'nb': backComponents,
              'min_corr': minCorr,
              'min_pnr': minPNR,
              'ring_size_factor': ringSize,
              'ssub_B': backDown,
              'normalize_init': False,                  # leave it True for 1p
              'update_background_components': False,    # improves results
              'method_deconvolution': 'oasis',          # could use 'cvxpy' alternatively
              'SNR_lowest': lowestSNR,
              'rval_thr': spaceThr,
              'gSig': neuronRadius,
              'gSiz': neuronBound,
           
        # params for OnACID:
              'ds_factor': spatDown_online,
              'epochs': epochs,
              'expected_comps': expectedNeurons_online,
              'init_batch': initFrames,
              'init_method':initMethod_online,  
              'min_SNR': minSNR_online,
              'motion_correct': motCorrection,
              'normalize': normalize_online,
              'save_online_movie': False,
              'show_movie': True,
              'update_num_comps': False,        # whether to search for new components
              'sniper_mode': cnnFlag,
              'thresh_CNN_noisy': thresh_CNN_noisy,

              
    }


allParams = params.CNMFParams(params_dict=initialParamsDict)    # define parameters in the params.CNMFParams
caimanResults = cnmf.online_cnmf.OnACID(params=allParams)       # pass parameters to caiman object


timer.toc()
# %% ********* Wait for initialization trigger message from MicroManager: *********
print("Now waiting for MicroManager to capture " + str(initFrames) + " initialization frames..")
pipeRead = open(receivePipeName, 'r')                # open the read pipe
triggerMessage_init = pipeRead.readline()[:-1]       # wait for message
print(triggerMessage_init)
expectedMessage_init = "startInitProcess"

#  ********* Start algorithm initialization if the message is right: *********
if triggerMessage_init == expectedMessage_init:
    print("*** Starting Initialization protocol with " + initMethod_online + " method ***")
    caimanResults.initialize_online()           # initialize model
else:
    print("*** WARNING *** INITIALIZATION FAILED ***")
    exit()
    
timer.toc()
# %% ********* Visualize results of initialization: *********
print("Initialization finished. Choose threshold parameter to adjust accepted/rejected components!")
logging.info('Number of components:' + str(caimanResults.estimates.A.shape[-1]))
visual = cm.load(fileToProcess[0], subindices=slice(0,500)).local_correlations(swap_dim=False)
caimanResults.estimates.plot_contours(img=visual)

#  ********* Use CNN clasifier to modify accepted/rejected components: *********
cnnThresh = 0.00001     # change threshold for CNN classifier to modify accepted/rejected components

# if true, pass through the CNN classifier with a low threshold (keeps clearer neuron shapes and excludes processes):
if cnnFlag:             
    allParams.set('quality', {'min_cnn_thr': cnnThresh})
    caimanResults.estimates.evaluate_components_CNN(allParams)
    caimanResults.estimates.plot_contours(img=visual, idx=caimanResults.estimates.idx_components)
    
# pause for user to decide on parameters
input("Press Enter after the parameter is chosen...")
# %% ********* Send message to MicroManager to trigger data streaming: *********   
triggerStream = "startStreamAcquisition\n"      # include new line at the end
pipeWrite = open(sendPipeName, 'w', 1)          # write (1 is for activating line buffering)
pipeWrite.write(triggerStream)          # write to pipe

print("CaImAn is ready for online analysis. Message was sent to MicroManager!")

timer.toc()
# %% ********* Wait for streaming analysis trigger message from MicroManager: *********    
pipeRead = open(receivePipeName, 'r')                   # open the read pipe
triggerMessage_analyse = pipeRead.readline()[:-1]       # wait for message
expectedMessage_analyse = "startStreamAnalysis"

#  ********* Start online analysis if the message is right: *********
if triggerMessage_analyse == expectedMessage_analyse:
    print("*** Starting online analysis with OnACID algorithm ***")
    caimanResults.fit_online()           # online analysis

# %% TO DO:
    # get output from fit_online()  # tried with monkeypatch -> it works well but values are not
                                    # what I expected, i.e. OnACID does not allow access to frame-by-frame
                                    # data easily.. have to wait for toolbox update
    # pass the values to stdpc






