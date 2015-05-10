""""
Demonstration Geometry Workshop :  Knot Detection
demo editor: Bertrand Kerautret
"""

from lib import base_app, build, http, image, config
from lib.misc import app_expose, ctime
from lib.base_app import init_app

import cherrypy
from cherrypy import TimeoutError
import os.path
import shutil
import time


class app(base_app):
    """ template demo app """

    title = "Knot detection based on angular analysis of z-motion"
    xlink_article = 'http://www.ipol.im/'
    xlink_src = 'http://ipol-geometry.loria.fr/SourceCodeDemosWorkshop/Segmentation_DGCI14.tgz'
    demo_src_filename = 'Segmentation_DGCI14.tgz'
    demo_src_dir = 'Segmentation_DGCI14'

    input_nb = 1 # number of input images
    input_max_pixels = 4096 * 4096 # max size (in pixels) of an input image
    input_max_weight = 1 * 4096 * 4096  # max size (in bytes) of an input file
    input_dtype = '3x8i' # input image expected data type
    input_ext = '.png'   # input image expected extension (ie file format)
    is_test = False      # switch to False for deployment
    commands = []
    def __init__(self):
        """
        app setup
        """
        # setup the parent class
        base_dir = os.path.dirname(os.path.abspath(__file__))
        base_app.__init__(self, base_dir)

        # select the base_app steps to expose
        # index() is generic
        app_expose(base_app.index)
        app_expose(base_app.input_select)
        app_expose(base_app.input_upload)
        # params() is modified from the template
        app_expose(base_app.params)
        # run() and result() must be defined here




    def build(self):
        """
        program build/update
        """
        # store common file path in variables
        tgz_file = self.dl_dir + self.demo_src_filename
        
        log_file = self.base_dir + "build.log"
        # get the latest source archive
        build.download(self.xlink_src, tgz_file)
        print "BEFIRE ECTRACT ...."
        # test if the dest file is missing, or too old
        if (os.path.isfile(self.bin_dir+'online_segfinal')
            and ctime(tgz_file) < ctime(self.bin_dir+'online_segfinal')):
            print "NON ECTRACT ...."
            cherrypy.log("not rebuild needed",
                         context='BUILD', traceback=False)
        else:
            # extract the archive
            print "ECTRACT ...."
            build.extract(tgz_file, self.src_dir)
            # build the program
            build.run("cd %s; gcc online_segfinal.c -lm -o online_segfinal;"%(self.src_dir+ self.demo_src_dir)\
                      , stdout=log_file)
            print "BUILD OK ...."
            # save into bin dir
            shutil.copy(os.path.join(self.src_dir+self.demo_src_dir,
                        "online_segfinal"), self.bin_dir)
            print "COPY OK ...."
            # cleanup the source dir
            shutil.rmtree(self.src_dir)
        return

    @cherrypy.expose
    @init_app
    def input_select(self, **kwargs):
        """
        use the selected available input images
        """
        self.init_cfg()
        #kwargs contains input_id.x and input_id.y
        input_id = kwargs.keys()[0].split('.')[0]
        assert input_id == kwargs.keys()[1].split('.')[0]
        # get the images
        input_dict = config.file_dict(self.input_dir)
        fnames = input_dict[input_id]['files'].split()
        for i in range(len(fnames)):
            shutil.copy(self.input_dir + fnames[i],
                        self.work_dir + 'input_%i' % i)
        if input_dict[input_id]['type'] == "3d":
            fnames = input_dict[input_id]['mesh'].split()
            for i in range(len(fnames)):
                shutil.copy(self.input_dir + fnames[i],
                            self.work_dir + 'inputMesh_%i' % i +'.obj')
        msg = self.process_input()
        self.log("input selected : %s" % input_id)
        self.cfg['meta']['original'] = False
        self.cfg.save()
        # jump to the params page
        return self.params(msg=msg, key=self.key)



    #---------------------------------------------------------------------------
    # Parameter handling (an optional crop).
    #---------------------------------------------------------------------------
    @cherrypy.expose
    @init_app
    def params(self, newrun=False, msg=None):
        """Parameter handling (optional crop)."""

        # if a new experiment on the same image, clone data
        if newrun:
            oldPath = self.work_dir + 'inputMesh_0.obj'
            self.clone_input()
            shutil.copy(oldPath, self.work_dir + 'inputMesh_0.obj')

        # save the input image as 'input_0_selection.png', the one to be used
        img = image(self.work_dir + 'input_0.png')
        img.save(self.work_dir + 'input_0_selection.png')
        img.save(self.work_dir + 'input_0_selection.pgm')


        # initialize subimage parameters
        self.cfg['param'] = {'x1':-1, 'y1':-1, 'x2':-1, 'y2':-1}
        self.cfg.save()
        return self.tmpl_out('params.html')


    @cherrypy.expose
    @init_app
    def wait(self, **kwargs):
        """
        params handling and run redirection
        """
     
        try:
            self.cfg['param'] = {'gridsize' : kwargs['gridsize'],
                                 'areathreshold' : kwargs['areathreshold'],
                                 'slenderness_ratio_threshold': kwargs['slenderness_ratio_threshold'],
                                 'minimum_length_threshold': kwargs['minimum_length_threshold']}
        except ValueError:
            return self.error(errcode='badparams',
                              errmsg="The parameters must be numeric.")

        http.refresh(self.base_url + 'run?key=%s' % self.key)
        return self.tmpl_out("wait.html")






    @cherrypy.expose
    @init_app
    def run(self):
        """
        algo execution
        """
        # read the parameters
        self.commands = ""
        # run the algorithm
        try:
            self.run_algo()
        except TimeoutError:
            return self.error(errcode='timeout',
                              errmsg="Try again with simpler images.")
        except RuntimeError:
            return self.error(errcode='runtime',
                              errmsg="Something went wrong with the program.")
        except ValueError:
            return self.error(errcode='badparams',
                              errmsg="The parameters given produce no contours,\
                              please change them.")

        http.redir_303(self.base_url + 'result?key=%s' % self.key)

        return self.tmpl_out("run.html")


    def run_algo(self):
        """
        the core algo runner
        could also be called by a batch processor
        this one needs no parameter
        """

        #----------
        # Getting params
        #----------
        param_g = self.cfg['param']['gridsize']
        param_a = self.cfg['param']['areathreshold']
        param_s = self.cfg['param']['slenderness_ratio_threshold']
        param_m = self.cfg['param']['minimum_length_threshold']

        command_args = ['online_segfinal', 'inputMesh_0.obj',  \
                         str(param_g), str(param_a), str(param_s), str(param_m) ]
                        
        logFile = open(self.work_dir + 'runlog.txt', "w") 
        self.cfg['param']['run_time'] = time.time()
        self.runCommand(command_args, stdOut=logFile)
        self.cfg['param']['run_time'] = time.time() - \
                                            self.cfg['param']['run_time']
        logFile.write(" \n")
        logFile.close()
        logFile = open(self.work_dir + 'runlog.txt', "r") 
        lines = logFile.readlines()
        line_cases = lines[1].split()
        self.cfg['param']['nbcomp'] = int(line_cases[3])
    
        logFile.close;
            


        fcommands = open(self.work_dir+"commands.txt", "w")
        fcommands.write(self.commands)
        fcommands.close()
        return


    @cherrypy.expose
    @init_app
    def result(self, public=None):
        """
        display the algo results
        """
        resultHeight = image(self.work_dir + 'input_0_selection.png').size[1]
        imageHeightResized = min (600, resultHeight)
        resultHeight = max(200, resultHeight)
        return self.tmpl_out("result.html", height=resultHeight, \
                             heightImageDisplay=imageHeightResized, \
                             width=image(self.work_dir\
                                           +'input_0_selection.png').size[0])


    def runCommand(self, command, stdOut=None, stdErr=None, comp=None,
                   outFileName=None):
        """
        Run command and update the attribute list_commands
        """
        p = self.run_proc(command, stderr=stdErr, stdout=stdOut, \
                          env={'LD_LIBRARY_PATH' : self.bin_dir})
        self.wait_proc(p, timeout=self.timeout)
        index = 0
        # transform convert.sh in it classic prog command (equivalent)
        for arg in command:
            if arg == "convert.sh" :
                command[index] = "convert"
            index = index + 1
        command_to_save = ' '.join(['"' + arg + '"' if ' ' in arg else arg
                 for arg in command ])
        if comp is not None:
            command_to_save += comp
        if outFileName is not None:
            command_to_save += ' > ' + outFileName

        self.commands +=  command_to_save + '\n'
        return command_to_save


    def commentsResultContourFile(self, command, fileStrContours, fileStrRes,
                                 sdp):
        """
        Add comments in the resulting contours (command line producing the file,
        or file format info)
        """

        contoursList = open (self.work_dir+"tmp.dat", "w")
        contoursList.write("# Set of resulting contours obtained from the " +\
                            "pgm2freeman algorithm. \n")
        if not sdp:
            contoursList.write( "# Each line corresponds to a digital "  + \
                                "contour " +  \
                                " given with the first point of the digital "+ \
                                "contour followed  by its freeman code "+ \
                                "associated to each move from a point to "+ \
                                "another (4 connected: code 0, 1, 2, and 3).\n")
        else:
            contoursList.write("# Each line represents a resulting polygon.\n"+\
                            "# All vertices (xi yi) are given in the same "+
                            " line: x0 y0 x1 y1 ... xn yn \n")
        contoursList.write( "# Command to reproduce the result of the "+\
                            "algorithm:\n")

        contoursList.write("# "+ command+'\n \n')
        f = open (fileStrContours, "r")
        index = 0
        for line in f:
            contoursList.write("# contour number: "+ str(index) + "\n")
            contoursList.write(line+"\n")
            index = index +1
        contoursList.close()
        f.close()
        shutil.copy(self.work_dir+'tmp.dat', fileStrRes)
        os.remove(self.work_dir+'tmp.dat')


