#-*- coding: utf-8 -*-
#!/usr/bin/env python
## @package location
# Location
# ========
# This is the main file to run during experiments.
# It implements the intrinsic, extrinsic and triangulation algorithms,
# the robot control and the audio and odometry measurements.
#
# The variables listed in the documentation are the ones that are
# the most likely to change for each setup. All other variables of
# the code should only be touched when necessary.
#
# created by Frederike Duembgen, September 2015

from __future__ import division
from __future__ import print_function

import calibrate as calib
import get_image as get
import marker_calibration as mark
import numpy as np
import matplotlib.pyplot as plt
import cv2
import time
import move
import Audio
import os
USAGE = '''
USAGE: locate.py -o <output dir> -i <input dir> [-m <number of points>]
[-f <fisheye on (0/1)>] [-d for debugging] [-h to show this help]

default:
m=6
f='0000'
d=0

In the debug mode, instead of accessing the cameras, a picture is loaded from the input path folder.
Name the picture has to be named N_imageX.png, where N is the step number (starting from 0)
and X is the camera number. for the extrinsic calibration, the image '_imageX.png' is used.
'''
DEBUG=0

EXTRINSIC='''Extrinsic calibration:
Enter camera number or 'q' to skip: '''
INTRINSIC='''Intrinsic calibration:
Enter camera number or 'q' to skip: '''
ROBOT_LOC='''Perform localization? ('y' for yes, 'n' to quit):
'''
ROBOT_VIS='''Visual localization :
Localize robot using cameras?  ('y' for yes or 'n' for no 'o' for old measurements)
'''
ROBOT_ODO='''Odometry localization :
Localize robot using odometry?  ('y' for yes or 'n' for no)
'''
ROBOT_ACO='''Acoustic localization :
Localize robot using acoustics? ('y' for yes or 'n' for no)
'''
ROBOT_MOVE='''Moving Robot         :
Do you want to move the robot? ('y' for yes or 'n' for no)
'''
ROBOT_REAL='''Real Robot           :
Do you want to save the real position? ('y' for yes or 'n' for no)
'''
## Radius of referencepoints (in pixels)
R_REF = 8
## Radius of robot point (in pixels)
R_ROB = 20
## Empiric threshold for circle detection robot
THRESH_ROB = 40
## Empiric threshold for circle detection reference points
THRESH_REF = 20
## Height of robot in mm
R_HEIGHT = 1650
## Number of cameras in camera combinations to be considered (2 to 4)
NUMBERS=range(2,5)


## HSV min for robot detection
MIN = np.array([150,100,0],dtype=np.uint8)
## HSV max for robot detection
MAX = np.array([10,250,255],dtype=np.uint8)
# res2:
#MIN = np.array([0,150,0],dtype=np.uint8)
#MAX = np.array([10,250,255],dtype=np.uint8)

## HSV min for reference point detection
MIN_REF = np.array([0,150,0],dtype=np.uint8)
## HSV max for reference point detection
MAX_REF = np.array([10,250,255],dtype=np.uint8)

## Margin from leftmost and downlost ref point to reference (in mm)
MARGIN = np.array([2000,2000],dtype=np.float)
## Coordinates of two basis points
PTS_BASIS = np.array(([2746,3066],[3506,2708]))
# res 2
# MARGIN = np.array([2000,1000],dtype=np.float) #margin from leftmost and downlost ref point to reference (in mm)
# PTS_BASIS = np.array(([2275,3769],[3128,3713])) #position of first and second reference points from wall (in mm)
# res 1
# MARGIN = np.array([1000,1000],dtype=np.float) #margin from leftmost and downlost ref point to reference (in mm)
# PTS_BASIS = np.array(([4000,1500],[2500,3000])) #position of first and second reference points from wall (in mm)



NCAMERAS = [139,141,143,145]# IP numbers of cameras to be considered
CHECKERBOARD = 0 # weather or not to use checkerboard for extrinsic calculation
WIDTH = 7 # width of checkerboard
HEIGHT = 5 # height of checkerboard
WIDTH_SENSOR = 3.67 #CCD sensor width in mm
FOCAL_MM = 3.6 #focal width in mm
WIDTH_IMG=1280#width of image in pixels

# Audio
N_CHANNELS=2 # number of channels to be used (1 or 2)
RATE = 44100 # sampling rate
CHUNK = 1024 # chunk size (in bit)
def get_param():
    global DEBUG
    global CHECKERBOARD
    ''' returns parameters from command line '''
    out_dir = ''
    in_dir = ''
    m = 0
    fisheye = '0000'
    try:
        opts,args = getopt.getopt(sys.argv[1:],"o:i:m:f:d",
                                  ['outdir=','indir=','m=','fisheye=','debug='])
    except getopt.GetoptError:
        print(USAGE)
        sys.exit(2)
    for opt, arg in opts:
        if opt == 'h':
            print(USAGE)
            sys.exit(2)
        if opt in ('--outdir',"-o"):
            out_dir = str(arg)
        if opt in ('--indir',"-i"):
            in_dir = str(arg)
        if opt in ('--m',"-m"):
            m = int(arg)
            if m==0: # checkerboard used for extrinsic
                CHECKERBOARD = 1
                m=WIDTH*HEIGHT
        if opt in ('--debug',"-d"):
            DEBUG=1
        if opt in ('--fisheye',"-f"):
            # array with '' for 0 and '1' for 1
            fish = np.array(arg.split('0'))
            # array with True and False
            fisheye = [c=='1' for c in fish[:4]]
            print("Fisheye settings for [139,141,143,145]:",fisheye[:4])
    if opts==[]:
        print(USAGE)
        sys.exit(2)
    if out_dir[-1]!="/":
        out_dir = out_dir+"/"
    if in_dir[-1]!="/":
        in_dir = in_dir+"/"
    return out_dir,in_dir,m,fisheye
def leastsquares(choice_ref,pts_ref,cams,errs,img,pts,r_real,loop_counter,TIME):
    '''
    Get least squares results from calibrate.py and plot errors vs.
    camera combinations
    '''

    # average error of reference point reprojection
    errors = np.matrix([round(np.sum(x)/len(x),4) for x in errs.values()])
    # create list of image points of chosen reference point in all cameras.
    pts_ref_list = []
    for values in pts_ref.values():
        pts_ref_list.append(values[choice_ref,:])
    # Calcualte reference point positions
    ref_obj = img.ref_obj[choice_ref,:] # real position of reference points


    p1,e21,__,arr = calib.get_leastsquares_combinations(NCAMERAS,NUMBERS,cams.values(),
                                    pts_ref_list,'hz',ref_obj[0,2],ref_obj)
    p2,e22,e32,__ = calib.get_leastsquares_combinations(NCAMERAS,NUMBERS,cams.values(),
                                    pts_ref_list,'hz','',ref_obj)
    # Calculate robot positions
    p3,e23,__,__ = calib.get_leastsquares_combinations(NCAMERAS,NUMBERS,cams.values(),
                                    pts.values(),'hz',R_HEIGHT,r_real)
    p4,e24,e34,__ = calib.get_leastsquares_combinations(NCAMERAS,NUMBERS,cams.values(),
                                    pts.values(),'hz','',r_real)

    names_errors="{0:5}\t{1:5}\t{2:5}".format("fixed","2D","3D")
    calib.save_combinations(out_dir,str(loop_counter)+"_combi_ref"+str(choice_ref)+TIME,
                            arr,p2,(e21,e22,e32),names_errors,
                            'Reference Point '+str(choice_ref))
    calib.save_combinations(out_dir,str(loop_counter)+"_combi_rob"+TIME
                            ,arr,p4,(e23,e24,e34),names_errors,'Robot')

    # Pick best combination based on 2D error with fixed height
    index2,err2 = calib.get_best_combination(e23)
    p_lq_fix = p3[index2]
    err1 = e23[index2]
    p_lq_free = np.matrix(p4[index2])
    err22 = e24[index2]
    err32 = e34[index2]
    print("real position:",r_real)

    # Results visualization and saving
    msg0="Best combination (based on best robot 2D error with fixed height):{0}, error: {1:6.0f}".format(arr[index2],err2)
    msg1="Fixed height [mm]: [{0:5.0f} , {1:5.0f} , {2:5.0f}], error 2D: {3:5.0f}".format(float(p_lq_fix[0]),float(p_lq_fix[1]),float(p_lq_fix[2]),err1)
    msg2="Free height [mm]:  [{0:5.0f} , {1:5.0f} , {2:5.0f}], error 2D: {3:5.0f} 3D: {4:5.0f}".format(float(p_lq_free[0]),float(p_lq_free[1]),float(p_lq_free[2]),err22,err32)
    msg3="Real position [mm]:[{0:5.0f} , {1:5.0f} , {2:5.0f}]".format(r_real[0,0],r_real[0,1],r_real[0,2])
    msg4="Error reference points [px]: {0} ".format(errors)
    print(msg0)
    print(msg1)
    print(msg2)
    print(msg3)
    print(msg4)
    with open(out_dir+str(loop_counter)+"_results_"+
                str(choice_ref)+'_'+TIME+".txt",'w') as f:
        f.write(msg0+"\n")
        f.write(msg1+"\n")
        f.write(msg2+"\n")
        f.write(msg3+"\n")
        f.write(msg4+"\n")

    return p_lq_fix, p_lq_free
def signal_handler(signal, frame):
    ''' Interrupt handler for stopping on KeyInterrupt '''
    print('Program stopped manually')
    sys.exit(2)

if __name__ == '__main__':
    print("updated")
    robot_connected=False
   # try:
    import sys
    import getopt
#---------------------------       Initialization       -------------------#
    # General
    out_dir,in_dir,NPTS,fisheye = get_param()
    if DEBUG:
        print("Running in DEBUG mode\n")
    else:
        print("Running in real mode\n")

    # if the already saved real positions should be used instead of
    # saving them manually. (save the file under 'posreal.txt')
    real_pos_file = ''
    if DEBUG:
        real_pos_file = np.loadtxt(in_dir+'posreal.txt')

    TIME = str(int(time.mktime(time.gmtime())))
    # Input positions.
    input_au =in_dir+"sound.wav"
    input_mov = in_dir+"control.txt"
    input_obj = in_dir+"objectpoints.csv"
    output_odo = out_dir+"odometry_"+TIME+".txt"
    output_tim = out_dir+"timings_"+TIME+".txt"
    output_au = out_dir+"audio_"+TIME+".wav"
    # Visual localization
    flag = 0 # alorithm for solvepnp (ITERATIVE:0, P3P:1, EPNP:2)
    r_wall = np.matrix([0,0,R_HEIGHT]) # real robot position from wall
    r_real = calib.change_wall_to_ref(PTS_BASIS,MARGIN,r_wall.copy())
    R_HEIGHT = r_real[0,2] #height of robot in mm
    choice_ref = 0 #chosen reference point for error calculation
    ref_z = 1*np.ones((1,NPTS)) # height of reference points
    #ref_z = np.array([135,0,230,0]) #height of reference points in mm
    #ref_z = '' #height automatically set to 0

    # Odometry
    loop_counter = ''


#--------------------------- 0. Intrinsic Calibration   -------------------#

    n = input(INTRINSIC)
    if n!='q':
        n=int(n)
        i=NCAMERAS.index(n)
        cam = calib.Camera(n)
        img_points,obj_points,size = cam.get_checkpoints(out_dir,5,8,fisheye)
        cam.calibrate(obj_points,img_points,size)
        f_theo=WIDTH_IMG*FOCAL_MM/WIDTH_SENSOR
        if (abs(cam.C[0,0]-f_theo)>100):
            choice = input("focal width obtained ({0}) far from theory {1}. Continue? (yes=y, no=n)".
                               format(int(cam.C[0,0]),f_theo))
            if choice == 'n':
                sys.exit(2)
        if (abs(cam.C[1,1]-f_theo)>100):
            choice = input("focal height obtained ({0}) far from theory {1}. Continue? (yes=y, no=n)".
                               format(int(cam.C[1,1]),f_theo))
            if choice == 'n':
                sys.exit(2)
        cam.save(in_dir,fisheye[i])
#--------------------------- 3. Extrinsic Calibration   -------------------#
    n = ''
    while True:
        n = input(EXTRINSIC)
        if n != 'q':
            result=1
            plt.close('all')
            n = int(n)
            cam = calib.Camera(n)
            cam.read(in_dir,fisheye)
            img=calib.Image(n)
            if DEBUG:
                for f in os.listdir(in_dir):
                    if f.startswith(str(loop_counter)+"_image_"+str(n)):
                        print(in_dir+f)
                        img.load_image(in_dir+f)
            else:
                img.take_image()

            # save unchanged image
            plt.imsave(out_dir+str(loop_counter)+'_image_'+str(n)+'_'+TIME,img.img)
            if not CHECKERBOARD:
                img.get_refimage(R_REF,THRESH_REF,MIN_REF,MAX_REF,NPTS,0,out_dir,
                                TIME)
                img.get_refobject(input_obj,NPTS,MARGIN,1,out_dir,TIME)
            else:
                result=img.get_checkerboard(in_dir,fisheye,WIDTH,HEIGHT,MARGIN,
                                        R_REF,THRESH_REF,MIN_REF,
                                        MAX_REF,1,out_dir,TIME)
            if result!=0:
                name='ref_'+str(n)+'_'+TIME+str('.txt')
                calib.write_ref(out_dir,name,img.ref_img,img.M,img.ref_obj)

            # save camera center
            img.ref_obj=img.ref_obj[:,:2]
            img.ref_obj=img.augment(img.ref_obj,ref_z)
            cam.reposition(img.ref_obj,img.ref_img,flag)
            fname="cameras_"+TIME
            cam.save_Center(in_dir,fname)
        else:
            break

#--------------------------- 4. Localization        -----------------------#
    loop_counter = 0
    times=0
    commands=''
    choice_loc = input(ROBOT_LOC)
    while choice_loc != "n":
#--------------------------- 4.1 Real Position    -------------------------#
        choice = input(ROBOT_REAL)
        if choice != 'n':
            if real_pos_file=='':
                x = input("robot position x in mm, measured from wall: ")
                y = input("robot position y in mm, measured from wall: ")
                if x!='':
                    r_wall[0,0]=x
                if y!='':
                    r_wall[0,1]=y
            else:
                r_wall[0,:2]=real_pos_file[loop_counter,:2]+20

            r_real = calib.change_wall_to_ref(PTS_BASIS,MARGIN,r_wall.copy())
            name='posreal_'+TIME+'.txt'
            calib.write_pos(out_dir,name,np.matrix(np.array(r_wall)[0]).reshape(((1,3))))
            name='posreal_ref_'+TIME+'.txt'
            calib.write_pos(out_dir,name,np.matrix(np.array(np.array(r_real)[0]).reshape((1,3))))

#--------------------------- 4.1 Visual localization ----------------------#
#--------------------------- 4.1.a Get Image Points  ----------------------#

        choice = input(ROBOT_VIS)
        if choice != 'n':
            plt.close('all')
            # save new robot position in file
            if choice == 'y':
                for i,n in enumerate(NCAMERAS):
                    img = calib.Image(n)

                    if DEBUG:
                        for f in os.listdir(in_dir):
                            if f.startswith(str(loop_counter)+"_image_"+str(n)):
                                img.load_image(in_dir+f)
                    else:
                        img.take_image()
                    # save unchanged image
                    plt.imsave(out_dir+str(loop_counter)+'_image_'+str(n)+'_'+TIME,img.img)

                    img.get_robotimage(R_ROB,THRESH_ROB,MIN,MAX,1,out_dir,
                                       TIME,loop_counter)
                    name='posimg_'+str(n)+'_'+TIME+'.txt'
                    calib.write_pos(out_dir,name,np.matrix(img.r_img).reshape((2,1)))
#--------------------------- 4.1.b Calculate Object Point -----------------#
            cams = dict()
            imgs = dict()
            pts = dict()
            pts_ref = dict()
            errs = dict()
            for i,n in enumerate(NCAMERAS):
                # Load camera
                cam = calib.Camera(n)
                cam.read(in_dir,fisheye[i])
                img = calib.Image(n)
                img.read_ref(out_dir,"ref_",NPTS)
                img.read_pos(out_dir,"posimg_")
                img.ref_obj = img.augment(img.ref_obj,ref_z)

                #--- Extrinsic calibration ---#
                err_img = 0
                cam.reposition(img.ref_obj,img.ref_img,flag)
                ref, err_img,lamda = cam.check_imagepoints(img.augment(img.ref_obj),
                                                        img.ref_img)
                #--- Individual Robot position ---#
                img.r_obj,err2,err3 = calib.get_leastsquares([cam],[img.augment(img.r_img)],
                                                        'hz',R_HEIGHT,r_real)
                imgs[i]=img
                cams[i]=cam
                pts[i]=img.augment(img.r_img)
                pts_ref[i]=img.augment(img.ref_img)
                errs[i]=err_img

            p_lq_fix,p_lq_free=leastsquares(choice_ref,pts_ref,cams,errs,img,pts,r_real,loop_counter,TIME)

            name='posobj_fix_'+str(choice_ref)+'_'+TIME+'.txt'
            p_lq_fix_wall = calib.change_ref_to_wall(PTS_BASIS,MARGIN,p_lq_fix.T[0])
            calib.write_pos(out_dir,name,p_lq_fix_wall[0])
            name='posobj_free_'+str(choice_ref)+'_'+TIME+'.txt'
            p_lq_free_wall = calib.change_ref_to_wall(PTS_BASIS,MARGIN,p_lq_free.T)
            calib.write_pos(out_dir,name,p_lq_free_wall[0])

#--------------------------- 4.2 Odometry Localization   ------------------#
        if DEBUG:
            choice='n'
        else:
            choice = input(ROBOT_ODO)
        if choice == 'y':

            # Connect to robot
            if not robot_connected:
                Robot = move.Robot()
                Robot.connect()
                robot_connected = True

            print("Odometry localization")
            Robot.get_position(output_odo)
#--------------------------- 4.3 Acoustic Localization   ------------------#
        if DEBUG:
            choice='n'
        else:
            choice = input(ROBOT_ACO)
        if choice == 'y':
            print("Acoustic localization")
            out_au = output_au.replace('/','/'+str(loop_counter)+'_')
            Au = Audio.Audio(input_au,out_au,N_CHANNELS,3,RATE,CHUNK)
            frames=Au.play_and_record_long()
            Au.save_wav_files(frames)
#--------------------------- 5. Make Robot Move        --------------------#
        if DEBUG:
            choice='n'
        else:
            choice = input(ROBOT_MOVE)
        if choice == 'y':
            if not robot_connected:
                Robot = move.Robot()
                Robot.connect()
                robot_connected = True
            if commands=='':
                (times, commands) = move.read_file(Robot,input_mov)
            if loop_counter > max(times.keys()):
                print("End of control input file reached.")
                break

            # only if motors are turned off at stop.
            #print("Activating motors")
            #Robot.activate()
            print("Moving robot")
            t = times[loop_counter]
            c = commands[loop_counter]
            Robot.move(t,c,output_tim)

        loop_counter += 1
        choice_loc = input(ROBOT_LOC)
#--------------------------- 6. Terminate               -------------------#
    # disconnect robot in the end.
    if robot_connected:
        Robot.cleanup()
        print("Robot cleaned up successfully")
    plt.close('all')
    print("Program terminated")
