"""
PyCarver
Authors:    Julio de la Cruz (jdelacru@andrew.cmu.edu)
            Era Vuksani (eravuksani@gmail.com)

This application is an easy to use and fast interface to carve partitions
and files from those partitions. Also it allows the user to recover
deleted files from the carved partitions.

PyCarver was made using tkinter and Python3.

References:
    Tkinter:
        - http://effbot.org/tkinterbook/tkinter-index.htm
    Tkinter tabs:
        Author:
        URL:
        - https://www.packtpub.com/mapt/book/application_development/
        9781785283758/2/ch02lvl1sec26/creating-tabbed-widgets
        - https://gist.github.com/mikofski/5851633
    TreeView:
        - http://knowpapa.com/ttk-treeview/
    MessageBox:
        - https://pythonspot.com/tk-message-box/
    Threading:
        - https://www.tutorialspoint.com/python/python_multithreading.htm

"""

import threading
import json
from queue import Queue
from datetime import datetime
from subprocess import Popen, PIPE
from os import walk, sep, listdir, path,linesep
from tkinter import ttk, messagebox
from tkinter.ttk import Notebook, Treeview
from tkinter.filedialog import askopenfilename, askdirectory, asksaveasfile
from tkinter import *


class Log:
    """ Logging for the outputs. """
    def __init__(self, logpath=None):
        """
        Setup log path and create log based on current timestamp.
        :param logpath: the path for the log file.
        :type logpath: str
        """
        if logpath is None:
            self.logpath = path.abspath(".")
        else:
            self.logpath = logpath

        #create log
        t = datetime.today().__format__("%Y-%m-%d_%H-%M-%S")
        filename = "pycarver_"+t+".log"
        self.logpath = path.join(self.logpath,filename)

        with open(self.logpath,"w+") as log:
            log.write("--- PyCarver Log --- (Created at "+t+")\n"+linesep)
        print("--- PyCarver Log --- (Created at "+t+")\n")

    def writeToLog(self, text):
        """
        Write something to the log with the current timestamp.
        :param text: text to output to file
        :type text: str
        """
        with open(self.logpath,"a") as log:
            log.write(datetime.today().__format__("%H:%M:%S")+": "+text+"\n"+linesep)


def mmlsParser(f):
    """
    Helper function to parse the output of mmls.
    :param f:   output of mmls
    :type f:    str
    :return info: list of json objects. Each json
                object contains info of each partition
                identified by mmls.
    :return bs: block size of each partition as identified by mmls
    :rtype info: list
    :rtype bs: int
    """

    info = []
    bs = -1

    slotFound = False
    partitionCounter = 0 #partitions carved

    for line in f:
        # find what the units are supposed to be
        if "Units are in " in line:
            bs = line[line.find("Units are in ") + len("Units are in "):line.find("-")]

        line = line.strip().split(" ")

        if (not slotFound):
            if ("Slot" in line):
                slotFound = True
        else:
            temp = {}
            temp['Slot'] = line[2]
            temp['CarvedFiles'] = "No"
            temp["FSType"] = ""
            temp["Path"] = ""
            temp["Carved"] = "No"

            if (line[2] == "Meta"):
                temp["Start"] = line[8]
                temp["End"] = line[11]
                temp["Length"] = line[14]
                temp["Description"] = " ".join(line[17:])
                temp["FileSystem"] = "No"

                # TODO: Add a number to distinguish between partitions
                # with the same name
                temp['Name'] = temp["Description"].replace(" ", "_")
            else:

                temp["Description"] = " ".join(line[14:])
                temp["Start"] = line[5]
                temp["End"] = line[8]
                temp["Length"] = line[11]

                if (":" in line[2]):
                    temp["Description"] += "_fs%d"%(partitionCounter)
                    temp["FileSystem"] = "Yes"

                    partitionCounter = partitionCounter + 1
                else:
                    temp["FileSystem"] = "No"

                temp['Name'] = temp["Description"].replace(" ", "_")


            info.append(temp)

    return info, bs


def fsstatParser(f):
    """
    Helper function to parse the output of fsstat.
    :param f: f is the output of fsstat
    :type f: str
    :return fsType:    This function will return the File System type of the
                        partition.
    :rtype fsType:  str
    """
    for line in f.splitlines():
        # find the partition type:
        indx = line.find("File System Type: ")
        if indx > -1:
            fsType = line[indx + len("File System Type: "):].strip()
            return fsType


def getFilesTree(path):
    """
    Function to get the folder hierarchy.
    :param path: The path of the folder to get the hierarchy of.
    :type path: str
    :return dir:    This function returns a Json object that contains
                the files and folders within the specified folder
    :rtype dir: str
    """
    dir = {}

    # list to store the directories found
    directories = []

    # Getting the files and directories in the given path
    # This will traverse the entire folder
    for (dirpath, dirnames, filenames) in walk(path):
        directories.append(dirpath)

        # Each directory will have an entry in the dictionary
        # that contains a list of its files
        dir[dirpath] = {}
        dir[dirpath]['Files'] = []
        for f in filenames:
            dir[dirpath]['Files'].append(dirpath + sep + f)

    directories.reverse()

    # We are done with these directories
    # They are now where they should
    done = []

    # Re positioning the directories under their parents
    for d in directories:
        for sub in directories:

            # We are not done with this sub directory
            if (sub not in done):

                # If the sub directory starts with a parent
                # path then we know that the subdirectory is a child
                # of directory d
                if (sub.startswith(d)):
                    if (sub != d):
                        # add the child to its parent entry
                        # and add it to the done list
                        dir[d][sub] = dir[sub]
                        done.append(sub)

                        # delete the child from the dir dictionary
                        # to avoid repetitions
                        del dir[sub]

    return dir


def addItems(tree, parent, dir, md5Path, md5=False, ):
    """
    Helper function to add items recursively to a TreeView object. THis
    function will add parents and its children.

    :param tree:    The TreeView object where the items are going to be
                    added
    :param parent:  The children (files) are going to be added below its
                    parent
    :param dir:     Json object containing the files and folders to be
                    presented in the TreeView
    :param md5:     Boolean variable that is True when md5 hash needs to
                    be calculated for each file or item and False
                    otherwise.

    :type tree:     Treeview
    :type parent:   Treeview child
    :type dir:      Dictionary
    :type md5:      Boolean
    """
    f = dir['Files']
    for i in f:
        # i is the path of each file
        vals = []
        if md5:
            vals.append(getMd5(i, md5Path))

        tree.insert(parent, "end", '', text=i.split(sep)[-1], values=(vals))

    for item in dir:
        if (item != "Files"):
            it = tree.insert(parent, "end", '', text=item.split(sep)[-1], values=([]))
            addItems(tree, it, dir[item], md5Path, md5=md5)

def getMd5(filePath, md5Path):
    """
    Helper function to calculate the md5 sum of the file in the given
    path.
    :param filePath: Path of the file being used in this function
    :type filePath: str
    :return md5: Returns the md5 sum of file in the given path
    :rtype md5: str
    """
    md5 = ""

    cmd = [md5Path, filePath]
    md5Output = Popen(cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = md5Output.communicate()

    stdout = stdout.decode("utf-8")
    stderr = stderr.decode("utf-8")

    if stdout:
        md5 = stdout.split(" ")[0]

    else:
        messagebox.showerror(stderr)

    return md5

class CarveThread(threading.Thread):
    """ Spawn thread when paritition is being carved."""

    def __init__(self, name, partitionsDict, app, pos, path, q):
        """
        Initialize the thread as follows:
        :param name:            The name given to the thread
        :param partitionsDict:  Array of dictionaries that contains all the
                                information about all the partitions
                                identified by mmls
        :param app:             The tkinter application
        :param pos:             Position of the partition inside the
                                partitionsDict
        :param path:            Path of the output folder
        :param q:               Queue to insert the commands used by each thread

        :type name:             str
        :type partitionsDict:   Array of dictionaries
        :type app:              App object
        :type pos:              Integer
        :type path:             str
        :type q:                Queue
        """
        threading.Thread.__init__(self)
        self.partitionsDict = partitionsDict
        self.name = name
        self.app = app
        self.pos = pos
        self.path = path
        self.queue = q

    def run(self):
        """
        Carve the file using the created thread.
        """
        print("CarveThread started: " + self.name)

        name = self.partitionsDict["Name"]
        outPath = self.path + "/" + name

        self.queue.put({"text": "Attempting to carve partition " + name + "...", "deli":"\t"})

        #the command that you want to run to carve the file
        cmd = [self.app.ddPath, "if=" + self.app.imagePath, "of=" + outPath, "bs=" + self.app.bs,
                "skip=" + self.partitionsDict["Start"], "count=" + self.partitionsDict["Length"]]

        #call dd to carve the file
        carvedPart = Popen(cmd, stdout=PIPE, stderr=PIPE)
        self.queue.put({"text": carvedPart.args, "deli": "$"})
        stdout, stderr = carvedPart.communicate()

        stdout = stdout.decode('utf-8')
        stderr = stderr.decode('utf-8')

        success = False

        if stdout:
            if "records" in stdout:
                self.app.insertCommand("Success!", "\t")
                self.queue.put({"text": "Success: " + name, "deli": "\t"})

                # success!
                success = True

                self.app.listOfPartitions[self.pos]["Carved"] = "Yes"
                self.app.listOfPartitions[self.pos]["Path"] = outPath
            else:
                if stderr:
                    if "records" in stdout:
                        # success!
                        self.queue.put({"text": "Success: " + name, "deli": "\t"})

                        success = True
                        self.app.listOfPartitions[self.pos]["Carved"] = "Yes"
                        self.app.listOfPartitions[self.pos]["Path"] = outPath
                else:
                    #failed to carve
                    self.queue.put({"text": "Failure: " + name, "deli": "\t"})
        else:
            if stderr:
                if "records" in stderr:
                    self.queue.put({"text": "Success: " + name, "deli": "\t"})

                    # success!
                    success = True

                    self.app.listOfPartitions[self.pos]["Carved"] = "Yes"
                    self.app.listOfPartitions[self.pos]["Path"] = outPath
                else:
                    # failed to carve
                    self.queue.put({"text": "Failure: " + name, "deli": "\t"})
            else:
                # failed to carve
                self.queue.put({"text": "Failure: " + name, "deli": "\t"})


        if self.partitionsDict['FileSystem'] == "Yes":
            fsType = Popen([self.app.fsstatPath, outPath], stdout=PIPE, stderr=PIPE)
            self.queue.put({"text": fsType.args, "deli": "$"})
            stdout, stderr = fsType.communicate()

            stdout = stdout.decode("utf-8")
            stderr = stderr.decode("utf-8")

            if stdout:
                type = fsstatParser(stdout)
                self.app.listOfPartitions[self.pos]["FSType"] = type
                #note: deli is delimiter
                self.queue.put({"text": "FSType: " + type, "deli": "\t"})
            else:
                self.queue.put({"text": "FSType: " + stderr, "deli": "\t"})

        print("Done: " + name)

class App: #TODO: call this GUI???
    """
    This is the main class of the tkinter application. It contains
    all the different functions to import the disk image and carve
    partitions and files.
    """
    def __init__(self, master):
        #create logger
        self.log = Log()

        self.master = master
        frame = Frame(master)

        self.topBtnWidth = 20

        self.imagePath = ''
        self.listOfPartitions = []

        self.partitionsToUse = []
        self.carveFileTypes = []


        self.scalpelDefault = "/usr/bin/scalpel"
        self.tskDefault = "/usr/bin/tsk_recover"
        self.mmlsDefault = "/usr/bin/mmls"
        self.md5Default = "/usr/bin/md5sum"
        self.ddDefault = "/bin/dd"
        self.fsstatDefault = "/usr/bin/fsstat"

        self.scalpelPath = self.scalpelDefault
        self.tskPath = self.tskDefault
        self.mmlsPath = self.mmlsDefault
        self.md5Path = self.md5Default
        self.ddPath = self.ddDefault
        self.fsstatPath = self.fsstatDefault

        # File types to use with SCALPEL
        self.FileTypes = ['jpg', 'gif', 'png' ,'pdf']

        self.notesFileName = None #notes file name

        #contains all of the carved file trees in the carved files window
        self.carvedFilesTrees = []

        # Table that will hold the partitions of the imported disk image
        # This will be displayed in the Right Frame
        self.partitionsOpenDiskTree = None

        # Table to show a summary of what the user has done with each
        # partition found in the imported disk image
        self.partitionsTree = None

        # Setting up the main window (frame) of the application
        master.geometry("{}x{}".format(master.winfo_screenwidth(), master.winfo_screenheight() - 100))
        master.title("PyCarver")
        master.resizable(False, False)

        # Top Frame that will hold the main buttons
        self.topFrame = Frame(master, height=100, bg="#DADADA")
        self.topFrame.pack_propagate(0)
        self.topFrame.pack(side=TOP, fill=X, pady=1)

        # Loading text
        loadVar = StringVar()
        self.loadingText = Label(self.topFrame, textvariable=loadVar, font=(None, 20))
        loadVar.set("Loading...")

        # Left Frame that will hold the summary TreeView
        self.leftFrame = Frame(master, bg="#DADADA", width=375, relief=SUNKEN)
        self.leftFrame.pack_propagate(0)
        self.leftFrame.pack(side=LEFT, fill=Y, padx=1)

        # Console Frame will contain all the commands executed by the
        # application and all related messages.
        self.consoleFrame = Frame(master, height=100, bg="black")
        self.consoleFrame.pack_propagate(0)
        self.consoleFrame.pack(side=BOTTOM, fill=X)

        # Scrollbar for the console
        scrollbar = Scrollbar(self.consoleFrame)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Text Widget of the console
        self.consoleText = Text(self.consoleFrame, yscrollcommand=scrollbar.set, bg='black',
                                foreground="white", borderwidth=2, relief="solid",
                                highlightthickness=0, state='disabled')

        self.consoleText.pack(expand=True, fill='both')

        scrollbar.config(command=self.consoleText.yview)

        # Right Frame to contain top tabs
        self.rightFrame = Frame(master, bg="white")
        self.rightFrame.pack_propagate(0)
        self.rightFrame.pack(side=RIGHT, expand=TRUE, fill=BOTH)

        # Where the tabs are going to be added: Tabs manager
        self.tabControl = Notebook(self.rightFrame, name="tabControl")
        self.tabControl.pack(expand=1, fill="both")

        self.addNotesTab()

        # button to import initial file
        self.insertButton = Button(self.topFrame, text="Import Disk Image",
                                   width=self.topBtnWidth, command=self.openDiskImage)
        self.insertButton.pack(side=LEFT, padx=10)

        # Button to carve paritions
        self.carvePartitionsButton = Button(self.topFrame, state=DISABLED,
                                            text="Carve Partitions", width=self.topBtnWidth,
                                            command=self.carvePartitionsWin)
        self.carvePartitionsButton.pack(side=LEFT, padx=10)


        # Button to recover deleted files
        self.recoverFilesButton = Button(self.topFrame, state=DISABLED,
                                         text="Recover Deleted Files", width=self.topBtnWidth,
                                         command=self.recoverFilesWin)
        self.recoverFilesButton.pack(side=LEFT, padx=10)

        # Button to Carve files
        self.carveFilesButton = Button(self.topFrame, state=DISABLED,
                                       text="Carve Files", width=self.topBtnWidth,
                                       command=self.carveFilesWin)

        self.carveFilesButton.pack(side=LEFT, padx=10)

        # Button to Carve files
        self.settingsButton = Button(self.topFrame,
                                       text="Settings", width=self.topBtnWidth,
                                       command=self.settings)

        self.settingsButton.pack(side=LEFT, padx=10)
    def openDiskImage(self):
        """
        Function to open a disk image, get the partitions in the image by
        using mmls and display the result in a TreeView object in a tab.
        """

        #show loading bar
        self.showLoading()

        diskImageLocation = askopenfilename(title="Choose file")

        if not diskImageLocation:
            self.hideLoading()
            return

        #run mmls on the disk image
        diskImageOut = Popen([self.mmlsPath, diskImageLocation], stdout=PIPE, stderr=PIPE)
        self.insertCommand(diskImageOut.args, "$")
        stdout, stderr = diskImageOut.communicate()

        if stdout:
            self.imagePath = diskImageLocation

            out = stdout.decode("utf-8")
            out = out.splitlines()
            self.listOfPartitions, self.bs = mmlsParser(out)

            if (len(self.listOfPartitions)):
                # Enabling the carvePartitionsButton button
                self.carvePartitionsButton['state'] = 'normal'

            # Creating the partitions tab
            self.partitionsTab = Frame(self.tabControl, name="partitions-tab", bg="white")

            # Close Tab button
            btn = Button(self.partitionsTab, text="Close Tab",
                         command=lambda t=str(self.partitionsTab): self.tabControl.forget(t))
            btn.place(relx=1, x=-15, y=2, anchor=NE)

            self.tabControl.add(self.partitionsTab, text="Disk Partitions")
            self.tabControl.select(self.partitionsTab)

            # This table (TreeView) will display the partitions in the tab
            self.partitionsOpenDiskTree = Treeview(self.partitionsTab, columns=("#", "Description", "FS Type", "MD5Sum"), show="headings",
                                selectmode="browse", height=23)

            yscrollB = Scrollbar(self.partitionsTab)
            yscrollB.pack(side=RIGHT, fill=Y)

            # Setting up columns
            self.partitionsOpenDiskTree.column("#", width=30)
            self.partitionsOpenDiskTree.column("Description", width=300)
            self.partitionsOpenDiskTree.column("FS Type", width=100)
            self.partitionsOpenDiskTree.column("MD5Sum", width=300)

            self.partitionsOpenDiskTree.heading("#", text="#")
            self.partitionsOpenDiskTree.heading("Description", text="Description")
            self.partitionsOpenDiskTree.heading("FS Type", text="FS Type")
            self.partitionsOpenDiskTree.heading("MD5Sum", text="MD5Sum")

            self.partitionsOpenDiskTree.configure(yscrollcommand=yscrollB.set)

            # Bind left click on text widget to copy_text_to_clipboard() function
            self.partitionsOpenDiskTree.bind("<ButtonRelease-1>",
                                             lambda event, t=self.partitionsOpenDiskTree: self.copyTextToClipboard(t))

            # Adding the entries to the TreeView
            for i in range(len(self.listOfPartitions)):
                self.partitionsOpenDiskTree.insert("", "end", i, values=(i, self.listOfPartitions[i]['Description'],
                                                                         "", ""),tags=str(i))

                # setup the two fields Carved and Recovered for each parition
                self.listOfPartitions[i]["Carved"] = "No"
                self.listOfPartitions[i]["Recovered"] = "No"
                self.listOfPartitions[i]["MD5Sum"] = ""

            self.partitionsOpenDiskTree.pack(anchor=NW, fill=Y)

        else:
            messagebox.showerror("Invalid Image", "Please try again with a valid image.")

        # Create the table to serve as storage for notifying state of partitions
        self.makeLefthandSideTable()
        self.refreshLeftSide()

        #loading is done
        self.hideLoading()

    def recoverFilesWin(self):
        """
        Pop up window to select the partitions to recover files
        """
        del self.partitionsToUse[:]

        # Creating the pop up window
        window = Toplevel(self.topFrame)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        # Creating the checkbox button for each file system
        for i in range(len(self.listOfPartitions)):
            # We just want to show the partitions corresponding to a
            # File System
            if (self.listOfPartitions[i]['FileSystem'] == "Yes"):
                v = IntVar()

                if (self.listOfPartitions[i]['Carved'] == "Yes"):
                    state = ACTIVE
                else:
                    state = DISABLED

                c = Checkbutton(window, text=self.listOfPartitions[i]['Description'], variable=v, height=1, width=30,
                                state=state, anchor=W)

                c.bind("<Button-1>", lambda event, self=self, i=i: self.recoverFilesCheck(self, i))
                c.pack()

        cancelButton = Button(window, text="Cancel", command=window.destroy)
        cancelButton.pack(side=LEFT)

        # recover the files
        recoverButton = Button(window, text="Recover!",
                               command=lambda self=self, window=window: self.recoverFiles(self, window))
        recoverButton.pack(side=RIGHT)

        window.mainloop()

        #print("Pressed 'recover files' button")

    def carvePartitionsWin(self):
        """
        Pop up window to select the partitions to carve
        """
        del self.partitionsToUse[:]

        # Creating the pop up window
        window = Toplevel(self.topFrame)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        # Creating the checkbox button for each file system
        for i in range(len(self.listOfPartitions)):
            v = IntVar()
            c = Checkbutton(window, text=self.listOfPartitions[i]['Description'],
                            variable=v, height=1, width=30, anchor=W)
            c.bind("<Button-1>", lambda event, self=self, i=i: self.carvePartitionsCheck(self, i))
            c.pack()

        cancelButton = Button(window, text="Cancel", command=window.destroy)
        cancelButton.pack(side=LEFT)

        # recover the files
        recoverButton = Button(window, text="Carve!", command=lambda s=self, window=window: self.carvePartitions(s, window))
        recoverButton.pack(side=RIGHT)

        window.mainloop()

        #print("Pressed 'carve files' button")

    def recoverFilesCheck(event, self, i):
        """
        This helper function will be called every time a partition
        is selected in the recover files pop up window. If the partition
        is selected it will remove it from the partitionsToUse array. If
        the partition is not selected then it will add it to the array.

        :param i:   The position of the partition in the array of partitions
        :param event: Not used, but is the event in question
        :type i:    int
        :type event: event
        """
        if (i in self.partitionsToUse):
            self.partitionsToUse.remove(i)
            print(i, "has been removed from the list")
        else:
            if self.listOfPartitions[i]["Carved"] == "Yes":
                self.partitionsToUse.append(i)
                print(i, "has been added from the list")

    def carvePartitionsCheck(event, self, i):
        """
        This helper function will be called every time a partition
        is selected in the carve partitions pop up window. If the partition
        is selected, it will remove it from the partitionsToUse array. If
        the partition is not selected then it will add it to the array.

        :param i:       The position of the partition in the array of partitions
        :param event:   Not used, but is the event in question
        :type i:        int
        :type event:    event.
        """

        print(event, self, i)

        if (i in self.partitionsToUse):
            self.partitionsToUse.remove(i)
            print(i, "has been removed from the list - carving")
        else:
            self.partitionsToUse.append(i)
            print(i, "has been added from the list - carving")

    def recoverFiles(event, self, window):
        """
        Function to recover the deleted files from the selected partitions.
        This function will run the tsk_recover command. If files are
        recovered, it will display a table with all the recovered files in
        a new tab. If no files are recovered then it will show the user
        a message.
        :param window: Pop up window of recover files
        :type window: tkinter window #todo: probably not correct type
        :param event: Not used, but is the event in question
        :type event: event #todo: probably not correct type
        """
        window.destroy()

        self.showLoading()

        #folder for output of tsk_recover call
        outFolder = askdirectory(title="Choose output folder")

        if not outFolder:
            messagebox.showerror("Error", "Please choose an output directory.")
            self.hideLoading()
            return

        # We recover the files for each selected partition
        for i in self.partitionsToUse:
            name = self.listOfPartitions[i]["Description"][:self.listOfPartitions[i]["Description"].find("(")].replace(" ","").replace("/","_")+\
                      "_"+str(i)

            self.insertCommand("Attempting to recover files from " + name + " partition...", "\t")

            partitionPath = self.listOfPartitions[i]['Path']

            if(partitionPath == None):
                self.insertCommand("Partition not carved. Carve the partition first and try again.", "\t")

                continue

            out = outFolder + "/out_" + name
            cmds = [self.tskPath, partitionPath, out]

            # Executing the command and getting its output
            recoveredPart = Popen(cmds, stdout=PIPE, stderr=PIPE)
            self.insertCommand(recoveredPart.args, "$")
            stdout, stderr = recoveredPart.communicate()

            partitionName = self.listOfPartitions[i]["Name"]

            if stdout:
                stdout = stdout.decode("utf-8")
                filesRecovered = int(stdout.split(":")[1])

                if filesRecovered:
                    dir = getFilesTree(out)

                    # Add new tab to show the output
                    self.recoverTab = Frame(self.tabControl, name="recover-tab-%s"%(partitionName), bg="white")

                    # Table to display the recovered files
                    tree = Treeview(self.recoverTab, height=23, columns=1)

                    # Close Tab button
                    btn = Button(self.recoverTab, text="Close Tab",
                                 command=lambda t=str(self.recoverTab): self.tabControl.forget(t))
                    btn.place(relx=1, x=-15, y=2, anchor=NE)

                    self.tabControl.add(self.recoverTab, text="Recovered Files")
                    self.tabControl.select(self.recoverTab)

                    self.insertCommand("Recovering files from selected partitions...", "\t")

                    self.carvedFilesTrees.append(tree)

                    yscrollB = Scrollbar(self.recoverTab)
                    yscrollB.pack(side=RIGHT, fill=Y)

                    tree.column("#0", width=400)
                    tree.heading("#0", text=out)

                    tree.column("#1", width=300)
                    tree.heading("#1", text="MD5 Hash")

                    tree.configure(yscrollcommand=yscrollB.set)

                    self.listOfPartitions[i]["Recovered"] = "Yes"

                    # Adding the items to the table
                    for key in dir:
                        parent = key.split(sep)[-1]
                        id2 = tree.insert("", "end", key, text=parent, values=([]))
                        addItems(tree, id2, dir[key], self.md5Path, md5=True)

                    tree.pack(anchor=NW)
                    tree.update_idletasks()

                else:
                    messagebox.showinfo("Recovered files summary",
                                        "No deleted files were recovered for partition: " + partitionName)

            else:
                self.listOfPartitions[i]["Recovered"] = "No"
                print(stderr)

            # update the pertaining info on the table
            self.changeTreeViewRow(i)

        self.hideLoading()

    def carvePartitions(event, self, window):
        """
        Function to carve the selected partitions, letting the user know
        upon success or failure. A new thread per partition
        will be spawned to carve each partition.

        :param window: Pop up window to select the partitions to carve
        :type window: tkinter window
        :param event: Not used, but is the event in question
        :type event: event
        """

        window.destroy()

        self.showLoading()

        # Carve selected partitions:
        print("Carving with dd")

        cmdsQueue = Queue()
        counter = 0
        threads = []

        succ = 0
        err = 0
        succMsg = "Partition(s) successfully carved:\n"
        errMsg = "Partition(s) unsuccessfully carved:\n"
        fsCarved = False

        outputFolderPath = askdirectory(title="Choose output folder")

        if not outputFolderPath:
            messagebox.showerror("Error", "Please choose an output folder.")
            self.hideLoading()
            return

        numPartitions = len(self.partitionsToUse)

        self.insertCommand("Carving "+str(numPartitions)+" partitions...", "\t")

        # Spawning a thread for each partition that needs to be carve
        # Adding parallelism to gain speed
        for i in self.partitionsToUse:
            partition = self.listOfPartitions[i]
            threads.append(CarveThread(partition["Slot"], partition, self, i, outputFolderPath, cmdsQueue))
            threads[counter].start()

            counter+=1

        # Waiting for all the threads to finish
        while threading.activeCount() > 1:
            if cmdsQueue.empty():
                continue
            else:
                cmd = cmdsQueue.get()
                self.insertCommand(cmd['text'], cmd['deli'])

        # Displaying all the used commands
        while not cmdsQueue.empty():
            cmd = cmdsQueue.get()
            self.insertCommand(cmd['text'], cmd['deli'])

        # Checking which partitions were successfully carved and which not
        for i in self.partitionsToUse:
            partition = self.listOfPartitions[i] #TODO: remove this extra variable
            if partition['Carved'] == "Yes":
                succMsg += "  - %s \n" % (partition['Description'])
                self.insertCommand("Partition saved in %s"%(partition['Path']), "\t")

                succ += 1
                print("path: ",partition["Path"])
                self.listOfPartitions[i]["MD5Sum"] = getMd5(partition["Path"], self.md5Path)
            else:
                errMsg += "  - %s \n" % (partition['Description'])
                err += 1

            # Updating the summary table
            self.changeTreeViewRow(i)
            self.changeTreeViewDiskPartitionsRow(i)

            if partition['FileSystem'] == "Yes":
                fsCarved = True

        if succ:
            if fsCarved:
                # If partitions were carved then we enable the
                # recover and carve files buttons
                self.recoverFilesButton['state'] = 'normal'
                self.carveFilesButton['state'] = 'normal'

            if(err):
                messagebox.showinfo("Carved Partitions Summary", succMsg + errMsg)
            else:
                messagebox.showinfo("Carved Partitions Summary", succMsg)
        else:
            messagebox.showerror("Carved Partitions Summary", errMsg)

        self.hideLoading()

    def refreshLeftSide(self):
        """
        Refresh the table that has information of what was carved, recovered, etc.
        #TODO: is this necessary?
        """

        for i in range(len(self.listOfPartitions)):
            self.partitionsTree.insert("", "end", i, values=(self.listOfPartitions[i]['Description'], 
                "X" if self.listOfPartitions[i]['Carved'] == "Yes" else "", 
                "X" if self.listOfPartitions[i]['Recovered'] == "Yes" else "", 
                "X" if self.listOfPartitions[i]['CarvedFiles'] == "Yes" else ""), tags=str(i))


    def changeTreeViewRow(self, i):
        """
        Change a row of the tree.
        :param i: the index value of the item to change
        :type i: Treeview.item #todo get real type
        :return:
        """

        childs = self.partitionsTree.get_children()
        if not childs:
            #no children to remove
            return
        for it in self.partitionsTree.get_children():
            print(self.partitionsTree.item(it))
            if i in self.partitionsTree.item(it)["tags"]:
                print("yes!")
                self.partitionsTree.item(it, values=(self.partitionsTree.item(it)["values"][0],
                    "X" if self.listOfPartitions[i]['Carved'] == "Yes" else "",
                    "X" if self.listOfPartitions[i]['Recovered'] == "Yes" else "",
                    "X" if self.listOfPartitions[i]['CarvedFiles'] == "Yes" else ""))
                return

    def changeTreeViewDiskPartitionsRow(self, i):
        """
        Change a row in the carved partitions table.
        :param i: index value of the item to change
        :type i: Treeview.item
        """

        for it in self.partitionsOpenDiskTree.get_children():
            if i in self.partitionsOpenDiskTree.item(it)["tags"]:
                self.partitionsOpenDiskTree.item(it, values=(self.partitionsOpenDiskTree.item(it)["values"][0],
                    self.partitionsOpenDiskTree.item(it)["values"][1],
                    self.listOfPartitions[i]['FSType'],
                    self.listOfPartitions[i]['MD5Sum']))
                return

    def addNotesTab(self):
        """
        Adds a tab that contains the notes of the project.
        """
        #Create tab
        self.notesTab = Frame(self.tabControl, name="notes-tab", bg="white")

        # Close Tab button -  closing this tab should not be allowed.
        # Instead, we have a save and a save as button.
        saveBtn = Button(self.notesTab, text="Save", command=self.saveNotes)
        saveAsBtn = Button(self.notesTab, text="Save As", command=self.saveAsNotes)
        saveAsBtn.place(relx=1, x=-2, y=2, anchor=NE)
        saveBtn.place(relx=1, x=-80, y=2, anchor=NE)

        # Adding the tab
        self.tabControl.add(self.notesTab, text="Notes")

        scrollbar = Scrollbar(self.notesTab)
        self.notes = Text(self.notesTab, yscrollcommand=scrollbar.set, bg="white",
                            foreground="black", borderwidth=2, relief="solid", highlightthickness=0)

        #insert cursor location
        self.notes.mark_set("sentinel", INSERT)
        self.notes.mark_gravity("sentinel", LEFT)

        self.notes.pack(expand=True, fill="y")

        scrollbar.config(command=self.notes.yview)

    def updateNotesTab(self,text):
        """
        Update notes tab by inserting text to it.
        :param text: text to insert
        :type text: str
        """
        self.notes.insert("END", text)
        self.notes.update_idletasks()

    def saveNotes(self):
        """
        Save the notes into the preselected file.
        """
        #saves a file
        if not self.notesFileName:
            self.saveAsNotes()
        else:
            try:
                with open(self.notesFileName, "w") as fp:
                    fp.write(str(self.notes.get(1.0, END)))  # starts from `1.0`, not `0.0`
                    self.insertCommand("Saved notes to " + self.notesFileName, "\t")
            except IOError as err:
                self.insertCommand("Could not save notes to " + self.notesFileName + " due to: " + err, "\t")

    def saveAsNotes(self):
        """
        Save the notes into a new file.
        """

        #saves a file as <filename>
        self.notesFileName = asksaveasfile(title="Save file as:", mode='w', defaultextension=".txt")
        tempName = self.notesFileName.name

        # asksaveasfile return `None` if dialog closed with "cancel".
        if self.notesFileName is None:
            self.insertCommand("Could not save notes to " + tempName, "\t")
            return
        try:
            # starts from `1.0`, not `0.0`
            self.notesFileName.write(str(self.notes.get(1.0, END)))
            self.notesFileName.close()
        except IOError as err:
            self.insertCommand("Could not save notes to " + tempName + " due to: " + err, "\t")
        self.notesFileName = tempName
        self.insertCommand("Saved notes to " + self.notesFileName, "\t")

    def makeLefthandSideTable(self):
        """
        Make the table that is shown on the left hand side of the screen.
        """
        #clear the frame to ensure that we have an empty space
        self.clearFrame(self.leftFrame)

        # make a new table on the left-hand side of the window
        self.partitionsTree = Treeview(self.leftFrame, columns=("Partition", "Crvd", "Rcovd", "Crvd Files"),
                                               show="headings", selectmode="none", height=len(self.listOfPartitions))

        self.partitionsTree.column("Partition", width=200)
        self.partitionsTree.heading("Partition", text="Partition")

        self.partitionsTree.column("Crvd", width=45)
        self.partitionsTree.heading("Crvd", text="Crvd")

        self.partitionsTree.column("Rcovd", width=45)
        self.partitionsTree.heading("Rcovd", text="Rcovd")

        self.partitionsTree.column("Crvd Files", width=80)
        self.partitionsTree.heading("Crvd Files", text="Crvd Files")

        self.partitionsTree.pack(anchor=NW, fill=Y)

        # Bind left click on text widget to copy_text_to_clipboard() function
        self.partitionsTree.bind("<ButtonRelease-1>", lambda event, t=self.partitionsTree: self.copyTextToClipboard(t))

    def clearFrame(self, frame):
        """
        Helper function to clear and delete all the children of a Frame.
        :param frame: Frame to be clear
        :type frame: Frame
        """
        for widget in frame.winfo_children():
            widget.destroy()

    def insertCommand(self, cmd, deli):
        """
        Helper function to insert a new command to the console frame.
        :param cmd: Command to insert
        :type cmd: str
        :param deli: Delimiter that will be placed in front of the command
        :type deli: str
        """
        if(type(cmd) == list):
            cmd = " ".join(cmd)

        #write to the command prompt
        self.consoleText.configure(state='normal')
        self.consoleText.insert(END, deli + " " + cmd + "\n")
        self.consoleText.configure(state='normal')
        self.consoleText.update_idletasks()
        self.consoleText.see("end")

        #save the command to the log
        self.log.writeToLog(deli + " " + cmd)

    def carveFilesWin(self):
        """
        Pop up window to select the type of files to recover
        """
        del self.carveFileTypes[:]

        # Creating the pop up window
        window = Toplevel(self.topFrame)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        options = []
        for j in range(len(self.listOfPartitions)):
            if (self.listOfPartitions[j]['FileSystem'] == "Yes"):
                if (self.listOfPartitions[j]['Carved'] == "Yes"):
                    # We just want to show the partitions corresponding
                    # to a File System
                    options.append("%d: %s"%(j, self.listOfPartitions[j]['Description']))

        self.dropVar = StringVar(window)
        self.dropVar.set(options[0])

        dropDown = OptionMenu(window, self.dropVar, *options)
        Label(window, text="Choose a partition: ").pack()

        dropDown.pack()

        # Creating the checkbox button for each file system
        for i in range(len(self.FileTypes)):
            v = IntVar()
            c = Checkbutton(window, text=self.FileTypes[i],
                            variable=v, height=1, width=30, anchor=W)
            c.bind("<Button-1>", lambda event, self=self, i=self.FileTypes[i]: self.carveFilesCheck(self, i))
            c.pack()

        cancelButton = Button(window, text="Cancel", command=window.destroy)
        cancelButton.pack(side=LEFT)

        # recover the files
        carveButton = Button(window, text="Carve Files",
                             command=lambda self=self, window=window: self.carveFiles(self, window))
        carveButton.pack(side=RIGHT)

        window.mainloop()

    def carveFilesCheck(event, self, t):
        """
        This helper function will be called every time a type of file
        is selected in the carve files pop up window. If the type
        is selected it will remove it from the carveFileTypes array. If
        the type is not selected then it will add it to the array.

        :param t:     Selected type
        :type t:      str
        :param event: the event that calls this function
        :type event:  event

        """
        if (t in self.carveFileTypes):
            self.carveFileTypes.remove(t)
            print(t, " has been removed from the list")
        else:
            self.carveFileTypes.append(t)
            print(t," has been added from the list")


    def carveFiles(event, self, window):
        """
        Function to carve the files out of the selected partition.
        This function will display the carved files, if any, in a table
        in a new tab.

        :param window:  Pop up window to select the types of files and
                        partition
        :type window:   tk.window
        :param event: the event that calls this function
        :type event:  event
        """
        window.destroy()

        self.showLoading()

        outFolder = askdirectory(title="Choose output folder")

        if not outFolder:
            messagebox.showerror("Error", "Please choose an output directory.")
            self.hideLoading()
            return


        partition = int(self.dropVar.get().split(":")[0])
        partitionPath = self.listOfPartitions[partition]['Path']

        # Creating the configuration file to be used by Scalpel
        newConfig = open("scal.config", "w")
        scalF = open("/etc/scalpel/scalpel.conf", "r")
        for line in scalF:
            if any(t in line for t in self.carveFileTypes):
                newConfig.write(line.replace("#", " "))

        scalF.close()
        newConfig.close()

        outputFileLocation = outFolder+sep+"carvedFiles_"+self.listOfPartitions[partition]["Description"]

        # Running the command and getting its output
        cmds = [self.scalpelPath, "-c", "./scal.config", partitionPath, "-o", outputFileLocation]
        recoveredPart = Popen(cmds, stdout=PIPE, stderr=PIPE)
        self.insertCommand(recoveredPart.args, "$")
        stdout, stderr = recoveredPart.communicate()

        stdout = stdout.decode("utf-8")
        stderr = stderr.decode("utf-8")

        if stdout:
            if stderr:
                if("ERROR" in stderr):
                    messagebox.showerror("Error", stderr)
                    self.hideLoading()
                    return

            filesCarved = int(stdout.split("files carved = ")[1].split(",")[0])

            messagebox.showinfo("Carved Files", "%d files were carved." % (filesCarved))
            if(filesCarved):
                self.listOfPartitions[partition]['CarvedFiles'] = "Yes"
                self.changeTreeViewRow(partition)
            else:
                self.hideLoading()
                return

            partitionName = self.listOfPartitions[partition]['Name']
            carvedFilesTab = Frame(self.tabControl, name="carvedFiles-tab-%s"%(partitionName), bg="white")

            # Close Tab button
            btn = Button(carvedFilesTab, text="Close Tab", command=lambda t=str(carvedFilesTab): self.tabControl.forget(t))
            btn.place(relx=1, x=-15, y=2, anchor=NE)

            self.tabControl.add(carvedFilesTab, text="Carved Files")
            self.tabControl.select(carvedFilesTab)

            dir = getFilesTree(outputFileLocation)

            # TreeView (Table)
            tree = Treeview(carvedFilesTab, height=23, columns=1)
            self.carvedFilesTrees.append(tree)

            yscrollB = Scrollbar(carvedFilesTab)
            yscrollB.pack(side=RIGHT, fill=Y)

            tree.column("#0", width=400)
            tree.heading("#0", text=outputFileLocation)

            tree.column("#1", width=300)
            tree.heading("#1", text="MD5 Hash")

            tree.configure(yscrollcommand=yscrollB.set)

            # Adding the items to the table
            for key in dir:
                parent = key.split(sep)[-1]
                id2 = tree.insert("", "end", key, text=parent, values=([]))
                addItems(tree, id2, dir[key], self.md5Path, md5=True)

            tree.pack(anchor=NW)


        else:
            messagebox.showerror("Error", stderr)


        self.hideLoading()

    #todo: figure out where this is getting called and put in tree
    def copyTextToClipboard(self, tree, event=None):
        """
        Copy the text to the clipboard
        :param tree: the tree to copy from
        :type tree: Treeview
        :param event: the event that calls this function
        :type event:  event
        """
        # triggered off left button click on text_field
        root.clipboard_clear()  # clear clipboard contents
        textList = tree.item(tree.focus())["values"]
        line = ""
        for text in textList:
            if line != "":
                line += ", " + str(text)
            else:
                line += str(text)

        root.clipboard_append(line)  # append new value to clipboard


    def showLoading(self):
        """
        Helper function to show the loading text.
        """
        self.loadingText.place(relx = 1, x = -20, y = 35, anchor = NE)

    def hideLoading(self):
        """
        Helper function to hide the loading text.
        """
        self.loadingText.place_forget()

    def settings(self):
        """
        Pop up window to change the path of the tools used by the program
        """
        # Creating the pop up window
        window = Toplevel(self.topFrame)
        window.protocol("WM_DELETE_WINDOW", window.destroy)

        # We need a frame for each row, because we are not using Tkinter grid
        scalpelFrame = Frame(window)
        tskFrame = Frame(window)
        mmlsFrame = Frame(window)
        md5Frame = Frame(window)
        ddFrame = Frame(window)
        fsstatFrame = Frame(window)

        # Variables to hold the text in the Entries
        self.scalpelVar = StringVar()
        self.tskVar = StringVar()
        self.mmlsVar = StringVar()
        self.md5Var = StringVar()
        self.ddVar = StringVar()
        self.fsstatVar = StringVar()

        # Entries to write the path of the tools
        scalpelEntry = Entry(scalpelFrame, textvariable=self.scalpelVar)
        tskEntry = Entry(tskFrame, textvariable=self.tskVar)
        mmlsEntry = Entry(mmlsFrame, textvariable=self.mmlsVar)
        md5Entry = Entry(md5Frame, textvariable=self.md5Var)
        ddEntry = Entry(ddFrame, textvariable=self.ddVar)
        fsstatEntry = Entry(fsstatFrame, textvariable=self.fsstatVar)

        # Info text in the pop up window
        Label(window, text="Insert the path of the following tools: ").pack(side=TOP)
        Label(window, text="Leave blank for default", font=(None, 10, "italic")).pack(side=TOP)
        Label(window, text="").pack(side=TOP)

        # Label next to the each Entry
        scalpelLabel = Label(scalpelFrame, text="Scalpel", width=10, anchor=W, padx=5)
        tskLabel = Label(tskFrame, text="tsk_recover", width=10, anchor=W, padx=5)
        mmlsLabel = Label(mmlsFrame, text="mmls", width=10, anchor=W, padx=5)
        md5Label = Label(md5Frame, text="md5sum", width=10, anchor=W, padx=5)
        ddLabel = Label(ddFrame, text="dd", width=10, anchor=W, padx=5)
        fsstatLabel = Label(fsstatFrame, text="fsstat", width=10, anchor=W, padx=5)


        # Packing and placing the Labels and Entries
        scalpelLabel.pack(side=LEFT)
        Label(scalpelFrame, text="(Default: %s)"%(self.scalpelDefault), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        scalpelEntry.pack(side=LEFT)

        tskLabel.pack(side=LEFT)
        Label(tskFrame, text="(Default: %s)"%(self.tskDefault), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        tskEntry.pack(side=LEFT)

        mmlsLabel.pack(side=LEFT)
        Label(mmlsFrame, text="(Default: %s)"%(self.mmlsDefault), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        mmlsEntry.pack(side=LEFT)

        md5Label.pack(side=LEFT)
        Label(md5Frame, text="(Default: %s)"%(self.md5Default), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        md5Entry.pack(side=LEFT)


        ddLabel.pack(side=LEFT)
        Label(ddFrame, text="(Default: %s)"%(self.ddDefault), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        ddEntry.pack(side=LEFT)

        fsstatLabel.pack(side=LEFT)
        Label(fsstatFrame, text="(Default: %s)"%(self.fsstatDefault), font=(None, 10, "italic"), width=25, anchor=W,
              padx=5, fg="gray").pack(side=LEFT)
        fsstatEntry.pack(side=LEFT)

        # Packing the frames
        scalpelFrame.pack(padx=10)
        tskFrame.pack(padx=10)
        mmlsFrame.pack(padx=10)
        md5Frame.pack(padx=10)
        ddFrame.pack(padx=10)
        fsstatFrame.pack(padx=10)

        # Cancel Button
        cancelButton = Button(window, text="Cancel", command=window.destroy)
        cancelButton.pack(side=LEFT)

        # Ok Button
        okButton = Button(window, text="Ok",
                               command=lambda s=self, window=window: self.changeSettings(s,window))
        okButton.pack(side=RIGHT)

        window.mainloop()

    def changeSettings(event, self, window):
        """
            Helper function to change the path of the tools we are using, if necessary
        """

        window.destroy()

        # Changing scalpel path
        if self.scalpelVar.get() == "":
            self.scalpelPath = self.scalpelDefault
        else:
            self.scalpelPath = self.scalpelVar.get()

        # Changing tsk_recover path
        if self.tskVar.get() == "":
            self.tskPath = self.tskDefault
        else:
            self.tskPath = self.tskVar.get()

        # Changing mmls Path
        if self.mmlsVar.get() == "":
            self.mmlsPath = self.mmlsDefault
        else:
            self.mmlsPath = self.mmlsVar.get()

        # Changing md5 path
        if self.md5Var.get() == "":
            self.md5Path = self.md5Default
        else:
            self.md5Path = self.md5Var.get()

        # Changing dd path
        if self.ddVar.get() == "":
            self.ddPath = self.ddDefault
        else:
            self.ddPath = self.ddVar.get()

        # Changing fsstat Path
        if self.fsstatVar.get() == "":
            self.fsstatPath = self.fsstatDefault
        else:
            self.fsstatPath = self.fsstatVar.get()

root = Tk()

app = App(root)

root.mainloop()