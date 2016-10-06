#!/usr/bin/python2

# ################################################################################################ #
# Dependency Listing script                                                                        #
# Author: Lazar Sumar                                                                              #
# Date:   10/04/2014                                                                               #
#                                                                                                  #
# This script will recursively go through the files in the directory extracting the #include       #
# filenames and information and collating it into a more easily readable format.                   #
# ################################################################################################ #

import sys
import os
import posixpath
import re
import string

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

import time
import sqlite3
from collections import OrderedDict
import json
from utility import Logger
from utility import toPosixPath
import argparse
import codecs

# ################################################################################################ #
# Script Classes                                                                                   #
# ################################################################################################ #
class DependencyScriptConfiguration(object):
    @staticmethod
    def GetConfigurationFilename(scriptFilename):
        path, ext = os.path.splitext(argv[0])
        path, name = os.path.split(path)
        return '{0}.ini'.format(name)

    def __init__(self, argv=None, argparser=None):
        # Make an argparser if we were not given one already.
        if argparser is None:
            self.argparser = argparse.ArgumentParser(description='Generates an SQLite3 database containing all of the #include dependencies in your project.')
        else:
            self.argparser = argparser
        
        # Add our arguments to the argparser.
        self.argparser.add_argument('-C', '--print-example-config', action='store_true', default=False, dest='printExampleConfig', help='The script requires a configuration file in the current directory or the script directory in order to run. This option generates an example config file that lists all the available options. Note: the databases must have the same filename in the config file. You will also want to make sure that the default filename, :memory:, is no longer set. If it was then you won\'t have a file to work with. Read the comments in the example config for details.')
        self.argparser.add_argument('--debug', action='store_true', default=False, dest='debugMessages', help='Print the debug messages. Very verbose, use only in development.')
        self.argparser.add_argument('--verbose', action='store_true', default=False, dest='verbose', help='Print the info messages about progress and status.')
        self.argparser.add_argument('--silence-errors', action='store_true', default=False, dest='silenceErrors', help='Don\'t print any errors.')
        self.argparser.add_argument('-c', '--config-filename', dest='scriptIni', metavar='<config-filename>', help='Specifies the path to the configuration file to use.')
        self.argparser.add_argument('-f', '--database-filename', dest='databaseFilename', metavar='<db-filename>', help='Specifies the filename of the database. Note: specifying this option overrides the filename in the configuration file.')
        self.argparser.add_argument('-s', '--source-path', dest='sourcePath', metavar='<source-path>', help='Specifies the path to the root of the source code.')
        
        # Configure the rest of our class. We need to initialize unused variables if we want to use
        # them later in our class.
        if argv is not None:
            self.Configure(argv)
        else:
            self.ClearConfiguration()

    def Configure(self, argv):
        self.args = argv
        self.messagePrinter = Logger()
        
        self.scriptPath, self.scriptExtension = os.path.splitext(argv[0])
        self.scriptPath, self.scriptName = os.path.split(self.scriptPath)
        
        self.argparser.parse_args(args=argv[1:], namespace=self)
        
        self.messagePrinter.isDbgEnabled = self.debugMessages
        self.messagePrinter.isInfoEnabled = self.verbose
        self.messagePrinter.isErrEnabled = not self.silenceErrors
        
        if self.scriptIni is None:
            iniPath = ''
            if self.scriptPath is not None:
                iniPath = self.scriptPath
            self.scriptIni = toPosixPath(os.path.join(iniPath, '{0}.ini'.format(self.scriptName)))
        
        self.parser = configparser.ConfigParser(allow_no_value = True) # see https://docs.python.org/2/library/configparser.html
        self.parser.optionxform = str # make case-sensitive as per https://docs.python.org/2/library/configparser.html
        
        self.isConfigured = True
        
        if os.path.exists(self.scriptIni):
            self.parser.read(self.scriptIni)
        elif os.path.exists(os.path.join(self.scriptPath, self.scriptIni)):
            self.parser.read(os.path.join(self.scriptPath, self.scriptIni))
        else:
            msg = "No configuration file found. Searched, current directory and script directory directory for {0}.".format(self.scriptIni)
            self.messagePrinter.error(msg)
            self.isConfigured = False
            
            self.databaseFilename = ':memory:'
            self.sourcePath = './'
            return
        
        try:
            if self.databaseFilename is None:
                self.databaseFilename = self.parser.get("Output", "DatabaseFilename")
        except:
            self.databaseFilename = ':memory:'
        
        try:
            if self.sourcePath is None:
                self.sourcePath = self.parser.get("Paths","SourceRoot")
                # Make the read SourceRoot path relative to the INI file's path.
                if self.isConfigured:
                    iniPath, iniFilename = os.path.split(self.scriptIni)
                    self.sourcePath = toPosixPath(os.path.normpath(os.path.join(iniPath, self.sourcePath)))
                    print('source-path: {0}'.format(self.sourcePath))
        except:
            self.sourcePath = './'
        
    def ClearConfiguration(self):
        self.args = None
        self.parser = None
        self.scriptName = None
        self.scriptPath = None
        self.scriptExtension = None
        self.scriptIni = None

class JsonProjectGroup(object):
    def __init__(self, name = None, description = None, projects = None, pathPrefix = None):
        self.name = name
        self.description = description
        self.projects = projects
        self.pathPrefix = pathPrefix
    
    def __str__(self):
        return "JsonProjectGroup(name = " + str(self.name) + ", description = " + str(self.description) + ", pathPrefix = " + str(self.pathPrefix) + ", projects = " + str(self.projects) + ")"
    
    def __repr__(self):
        return str(self)
    
class JsonProject(object):
    def __init__(self, name = None, path = None, includePath = None, dependencies = None):
        self.name = name
        self.path = path
        self.includePath = includePath
        self.dependencies = dependencies
        
    def __str__(self):
        return "JsonProject(name = " + str(self.name) + ", path = " + str(self.path) + ", includePath = " + str(self.includePath) + ", dependencies = " + str(self.dependencies) + ")"
        
    def __repr__(self):
        return str(self)

def GroupInfo_JSONObjectHook(dictionary):
    if 'type' in dictionary:
        if dictionary['type'] == 'group':
            # Optional items
            pathPrefix = None
            if 'path-prefix' in dictionary:
                pathPrefix = dictionary['path-prefix']
            
            return JsonProjectGroup(dictionary['name'], dictionary['description'], dictionary['projects'], pathPrefix)
        elif dictionary['type'] == 'project':
            # Optional items
            includePath = None
            if 'include-path' in dictionary:
                includePath = dictionary['include-path']
            
            return JsonProject(dictionary['name'], dictionary['path'], includePath, dictionary['dependencies'])
        elif dictionary['type'] == 'list':
            return dictionary['object']
    return dictionary
        
class SolutionInfo(object):
    def __init__(self, config = None):
        self._jsonObjectHooks = { "ProjectGroupsList" : GroupInfo_JSONObjectHook }
        
        if not config:
            self.path = None
            self.projectList = None
        else:
            self.Configure(config)
    
    
    def Configure(self, config):
        self.path = config.sourcePath
        
        # os.path.abspath() call prefixes the path with a drive letter.
        # os.path.isabs() does not check for the drive letter so cannot be used as a normalization check.
        self.path = os.path.abspath(self.path)
        self.path = os.path.normpath(self.path)
        
        sectionName = "JSONObjects"
        self.jsonObjectStrings = OrderedDict(config.parser.items(sectionName))
        self.jsonObjects = OrderedDict()
        
        for p in self.jsonObjectStrings:
            try:
                if p in self._jsonObjectHooks:
                    self.jsonObjects[p] = json.loads(self.jsonObjectStrings[p], object_hook=self._jsonObjectHooks[p])
                else:
                    self.jsonObjects[p] = json.loads(self.jsonObjectStrings[p])
            except Exception as e:
                config.messagePrinter.error("The [{0}] option in the [{1}] section has an invalid JSON object!".format(p, sectionName))
                config.messagePrinter.dbg("Exception message: {0}".format(e))
                config.messagePrinter.error("Exiting.")
                sys.exit(1)
        
        
        self.projectList = OrderedDict()
        self.jsonObjects["ProjectGroupsList"]
        
        for group in self.jsonObjects["ProjectGroupsList"]:
            if config.sourcePath is not None:
                if group.pathPrefix is not None:
                    groupPathPrefix = group.pathPrefix = toPosixPath(os.path.normpath(os.path.join(config.sourcePath, group.pathPrefix)))
                else:
                    groupPathPrefix = config.sourcePath
            else:
                groupPathPrefix = None
            
            for project in group.projects:
                # Add the project reverse link back to group.
                project.groupName = group.name
                
                # Apply the group's path-prefix property to each project path.
                if groupPathPrefix is not None:
                    project.path = toPosixPath(os.path.normpath(os.path.join(groupPathPrefix, project.path)))
                    if project.includePath is not None and len(project.includePath) > 0:
                        project.includePath = toPosixPath(os.path.normpath(os.path.join(groupPathPrefix, project.includePath)))
                
                if group.pathPrefix is not None and not os.path.isdir(group.pathPrefix):
                    config.messagePrinter.error("The group \"{0}\" path-prefix \"{1}\" does not exist.".format(group.name, group.pathPrefix))
                if not os.path.isdir(project.path):
                    config.messagePrinter.error("The project \"{0}\" path \"{1}\" does not exist.".format(project.name, project.path))
                if project.includePath is not None and not os.path.isdir(project.includePath):
                    config.messagePrinter.error("The project \"{0}\" include-path \"{1}\" does not exist.".format(project.name, project.includePath))
                
                # Add the project to the dictionary
                self.projectList[project.name] = project
        
    # filepath is either absolute or relative to the cwd.
    def GetPathRelativeToSolution(self, filepath):
        if not os.path.isabs(filepath):
            filepath = os.path.abspath(filepath)
        
        filepath = os.path.normpath(filepath)
        filepath = os.path.relpath(filepath, self.path)
        
        return toPosixPath(filepath)
    
    def GetPathRelativeToProject(self, filepath, projectName):
        if not os.path.isabs(filepath):
            filepath = os.path.abspath(filepath)
        
        filepath = os.path.normpath(filepath)
        
        if projectName in self.projectList:
            relProjectPath = self.projectList[projectName].path
            absProjectPath = os.path.join(self.path, relProjectPath)
            filepath = os.path.normpath(absProjectPath)
            filepath = os.path.relpath(filepath, absProjectPath)
            
            return filepath
        
        return None
    
    # GetProjectName
    #   Computes the most likely project that the file belongs to on the basis of the file path
    #   given.
    #  
    #   filepath should be an absolute path, if it is not it is taken to be relative to the cwd.
    def GetProjectName(self, filepath):
        if not os.path.isabs(filepath):
            filepath = os.path.abspath(filepath)

        filepath = os.path.normpath(filepath)
        filepath = toPosixPath(filepath) # Standardise the slashes.
        if filepath[-1] != '/': # Ensure that the path is slash terminated otherwise we might
                                # end up including projects which start with the same name...
            filepath += '/'
            
        rv = None # Project name
        rvLen = 0 # Lenght of the matched path
        
        # Project paths are either absolute or relative to the solution path.
        for project in self.projectList:
            projectPath = self.projectList[project].path
            if not os.path.isabs(projectPath):
                projectPath = os.path.abspath(projectPath)
            
            projectPath = os.path.normpath(projectPath)
            projectPath = toPosixPath(projectPath) # Standardise the slashes.
            if projectPath[-1] != '/': # Ensure that the path is slash terminated otherwise we might
                                       # end up including projects which start with the same name...
                projectPath += '/'
            
            # Check all projects in the list and return the one with the longest matching path.
            if filepath.startswith(projectPath):
                if not rv:
                    rv = project
                    rvLen = len(projectPath)
                else:
                    if rvLen < len(projectPath):
                        rv = project
                        rvLen = len(projectPath)
        
        return rv
    
    def GetSolutionPath(self):
        return self.path
        
    def GetProjectList(self):
        rv = []
        
        for p in self.projectList:
            rv.append(p)
        
        return rv
    
    def GetProjectPath(self, projectName):
        return self.projectList[projectName].path
    
    def GetProjectSortOrder(self, projectName):
        i = 0
        
        for p in self.projectList:
            if projectName == p:
                break
            i = i + 1
        
        if i == len(self.projectList):
            return None
            
        return i
    
    def HasProjectDependency(self, projectName, projectDependency):
        if projectName in self.projectList:
            return (projectDependency in self.projectList[projectName].dependencies)
        return None
    
    def HasProjectDependent(self, projectName, projectDependent):
        if projectDependent in self.projectList:
            return (projectName in self.projectList[projectDependent].dependencies)
        return None
        
    def GetJsonProjectGroupsString(self):
        if "ProjectGroupsList" in self.jsonObjectStrings:
            return self.jsonObjectStrings["ProjectGroupsList"]
        return None

class DependencyScriptDatabase(object):
    def __init__(self, filename = None, errorLogger = None, messagePrinter = None):
        self._projectDropCommand = """
DROP TABLE IF EXISTS Project;
"""

        self._projectCreateCommand = """
CREATE TABLE IF NOT EXISTS Project (
    SolutionPath TEXT PRIMARY KEY,
    Name TEXT,
    HierarchyLevel INTEGER
);
"""
    
        self._codeFileDropCommand = """
DROP TABLE IF EXISTS CodeFile;
"""

        self._codeFileCreateCommand = """
CREATE TABLE IF NOT EXISTS CodeFile (
    SolutionPath TEXT PRIMARY KEY,
    Project TEXT,
    Filename TEXT
);
"""

        self._includeDirectiveDropCommand = """
DROP TABLE IF EXISTS IncludeDirective;
"""

        self._includeDirectiveCreateCommand = """
CREATE TABLE IF NOT EXISTS IncludeDirective (
    CodeFileSolutionPath TEXT,
    IncludeText TEXT,
    IncludeType TEXT,
    IncludeFilename TEXT,
    IncludeProject TEXT,
    IncludeSolutionPath TEXT,
    LineNumber INTEGER
);
"""

        self.filename = filename
        self.isOpen = False
        self.includeTypeLocal = "local"
        self.includeTypeSystem = "system"
        self.errorLogger = errorLogger
        self.messagePrinter = messagePrinter
        
    def DeleteFile(self, filename = None):
        if filename and filename != self.filename:
            self.filename = filename
        else:
            self.Abort()
            self.Close()
        
        if self.filename:
            if self.messagePrinter:
                self.messagePrinter.info("Deleting: " + str(self.filename))
            os.remove(self.filename)
            
        if self.dirPath:
            if self.messagePrinter:
                self.messagePrinter.info("Removing: " + str(self.dirPath))
            os.rmdir(self.dirPath)
        
    def Open(self, filename = None):
        if filename and filename != self.filename:
            if self.isOpen:
                self.Abort()
                self.Close()
            self.filename = filename

        if not self.isOpen and self.filename:
            if self.messagePrinter:
                self.messagePrinter.info("Database filename: " + str(self.filename))
            
            # Ensure that the directory exists
            dbPath, dbFilename = os.path.split(self.filename)
            if dbPath and not os.path.exists(dbPath):
                if self.messagePrinter:
                    self.messagePrinter.info("Making directory: " + str(dbPath))
                os.mkdir(dbPath)
                self.dirPath = dbPath
            
            self.con = sqlite3.connect(self.filename)
            self.cur = self.con.cursor()
            
            self.isOpen = True
            if self.messagePrinter:
                self.messagePrinter.info("Database opened.")
            
        return self.isOpen

    def Drop(self):
        self.cur.execute(self._projectDropCommand)
        self.cur.execute(self._codeFileDropCommand)
        self.cur.execute(self._includeDirectiveDropCommand)
        self.con.commit()
        
    def Create(self):
        self.cur.execute(self._projectCreateCommand)
        self.cur.execute(self._codeFileCreateCommand)
        self.cur.execute(self._includeDirectiveCreateCommand)
        self.con.commit()
        
    def Abort(self):
        if self.isOpen:
            self.con.rollback()
            if self.messagePrinter:
                self.messagePrinter.info("Database rolled back.")
        
    def SaveProgress(self):
        if self.isOpen:
            self.con.commit()
        
    def Close(self):
        if self.isOpen:
            self.con.commit()
            self.con.close()
            self.isOpen = False
            self.con = None
            self.cur = None
            if self.messagePrinter:
                self.messagePrinter.info("Database closed.")
        
    def SetFilename(self, filename):
        self.filename = filename

    def GetFile(self, solutionPath):
        self.cur.execute("SELECT * FROM CodeFile WHERE SolutionPath = ?", (solutionPath,))
        return self.cur.fetchone()
    
    def GetFilesEndingWith(self, incompletePath):
        self.cur.execute("SELECT * FROM CodeFile WHERE SolutionPath like ?", ('%' + incompletePath,))
        return self.cur.fetchall()
        
    def AddProject(self, projectName, solutionPath, hierarchyLevel):
        solutionPath = toPosixPath(solutionPath) # normpath doesn't normalize to posix slashes.
        
        try:
            self.cur.execute("INSERT INTO Project (SolutionPath, Name, HierarchyLevel) VALUES (?, ?, ?);", (solutionPath, projectName, hierarchyLevel))
        except:
            self.cur.execute("UPDATE CodeFile SET Name = ?, HierarchyLevel = ? WHERE SolutionPath = ?;", (projectName, hierarchyLevel, solutionPath))
        
        return self.cur.lastrowid
        
    def AddFile(self, filename, project, solutionPath, exists):
        solutionPath = toPosixPath(solutionPath) # normpath doesn't normalize to posix slashes.
        
        try:
            self.cur.execute("INSERT INTO CodeFile (SolutionPath, Project, Filename) VALUES (?, ?, ?);", (solutionPath, project, filename))
        except:
            self.cur.execute("UPDATE CodeFile SET Project = ?, Filename = ? WHERE SolutionPath = ?;", (project, filename, solutionPath))
        
        return self.cur.lastrowid

    def AddInclude(self, solutionPath, includeText, includeType, includeFilename, includeProject, includeSolutionPath, lineNumber):
        solutionPath = toPosixPath(solutionPath) # normpath doesn't normalize to posix slashes.
        normIncludeText = toPosixPath(includeText) # normpath doesn't normalize to posix slashes.
        if includeSolutionPath:
            includeSolutionPath = toPosixPath(includeSolutionPath) # normpath doesn't normalize to posix slashes
        
        if normIncludeText != includeText:
            if self.errorLogger:
                self.errorLogger.write("Error, #include directive with non-posix path!" + includeText + " included in " + solutionPath + "\n")
            includeText = normIncludeText
        
        try:
            self.cur.execute("INSERT INTO IncludeDirective (CodeFileSolutionPath, IncludeText, IncludeType, IncludeFilename, IncludeProject, IncludeSolutionPath, LineNumber) VALUES (?, ?, ?, ?, ?, ?, ?);", (solutionPath, includeText, includeType, includeFilename, includeProject, includeSolutionPath, lineNumber))
        except:
            if self.messagePrinter:
                msg = "Unknown exception for: INSERT INTO IncludeDirective (CodeFileSolutionPath, IncludeText, IncludeType, IncludeFilename, IncludeProject, IncludeSolutionPath) VALUES (" + repr(solutionPath) + "," + repr(includeText) + "," + repr(includeType) + "," + repr(includeFilename) + "," + repr(includeProject) + "," + repr(includeSolutionPath) + "," + repr(lineNumber) + ");"
                self.messagePrinter.info(msg)
        
        return self.cur.lastrowid
    
    # Returns a dictionary of projects mapped to their sets of dependencies.
    #   dictionary keys:  Project names (strings)
    #   dictionary value: A set of project names (set() containing project name strings)
    def QueryProjectDependencieTree(self):
        if self.isOpen:
            dependencyTree = OrderedDict()
            
            self.cur.execute("""
                SELECT c.Project as Project, i.IncludeProject as Dependency 
                FROM CodeFile c
                INNER JOIN IncludeDirective i ON c.SolutionPath = i.CodeFileSolutionPath 
                WHERE c.Project IS NOT NULL AND i.IncludeProject IS NOT NULL
                GROUP BY c.Project, i.IncludeProject;
                """)
            
            row = self.cur.fetchone()
            while row:
                if row[0] not in dependencyTree:
                    dependencyTree[row[0]] = set()
                try:
                    dependencyTree[row[0]].add(row[1])
                except:
                    pass # It would be odd but not an error for this line to be executed.
                
                row = self.cur.fetchone()

            for project in dependencyTree:
                dependencyTree[project].discard(project)
            
            return dependencyTree
        
        return None
        
# FileFilter class
#   The file filter class is a wrapper for two lists of regular expressions that are used to
#   specify which files are to be included and which files are to be excluded from processing.
class FileFilter(object):
    def __init__(self, config = None):
        if not config:
            self.includeList = [ ".*\\.cpp$", ".*\\.h$", ".*\\.hpp$", ".*\\.c$" ]
            self.excludeList = [ ".*moc_.*" ]
        else:
            self.Configure(config)
    
    def Configure(self, config):
        if config.parser:
            if config.parser.has_section("FileFilter"):
                if config.parser.has_option("FileFilter", "IncludePatterns"):
                    self.includeList = config.parser.get("FileFilter", "IncludePatterns").split()
                if config.parser.has_option("FileFilter", "ExcludePatterns"):
                    self.excludeList = config.parser.get("FileFilter", "ExcludePatterns").split()
    
    def _MatchAnyPatternInList(self, patternList, string):
        for pattern in patternList:
            matchObj = re.match(pattern, string)
            if matchObj:
                return True

        return False

    def IsExcluded(self, filepath):
        if not self.excludeList:
            # An empty list means that nothing is excluded
            return False
        return self._MatchAnyPatternInList(self.excludeList, filepath)
        
    def IsIncluded(self, filepath):
        if not self.includeList:
            # An empty list means that everything is included.
            return True
        return self._MatchAnyPatternInList(self.includeList, filepath)
        
class SolutionProcessor(object):
    # match.group(1) will contain the #include content including {<,>,"}
    # match.group(2) will contain the included filepath only for system includes (None otherwise)
    # match.group(3) will contain the included filepath only for local includes (None otherwise)
    includeRegex = re.compile('^[ ]*#include[ ]+(\\<(.*?)\\>|"(.*?)")')

    def __init__(self, config = None, fileFilter = None):
        self.config = config
        self.fileFilter = fileFilter
        self.solutionInfo = SolutionInfo(config)
        self.database = DependencyScriptDatabase(config.databaseFilename, messagePrinter=config.messagePrinter)
        self.htmlFilename = config.parser.get("Output", "HtmlFilename")
        self.isDbOpen = False

    # GetIncludes free-function (equivalent to a static class method)
    #   This function processes a .h, .c, .hpp, .cpp; file, extracts all of the #include'd file paths,
    #   categorises them into two lists (local and system includes) and returns the two lists in a tuple.
    def GetIncludes(self, filepath):
        localIncludes = []
        systemIncludes = []
        
        try:
            reader = open(filepath)
        except IOError as e:
            self.config.messagePrinter.error("Error, couldn't open" + repr(filepath))
            sys.exit(1)
        
        # Read the file, line by line
        line = reader.readline();
        lineNum = 0
        while line:
            lineNum += 1
            # Check the include regex
            matchObj = self.includeRegex.match(line)
            if matchObj:
                if matchObj.group(2) is not None:
                    systemIncludes.append((matchObj.group(2), lineNum))
                elif matchObj.group(3) is not None:
                    localIncludes.append((matchObj.group(3), lineNum))
                
            line = reader.readline();
        
        reader.close()
        
        return (localIncludes, systemIncludes)
        
    def GetIncludeFileAbsolutePath(self, absoluteFilepath, includetext, isLocalInclude = True):
        filepath, filename = os.path.split(absoluteFilepath)
        
        localFilePath = os.path.join(filepath, includetext)
        solFilePath = os.path.join(self.solutionInfo.path, includetext)
        
        if os.path.isfile(localFilePath):
            # This is a local include file
            return os.path.abspath(localFilePath)
        elif os.path.isfile(solFilePath):
            # Solution path relative include
            return os.path.abspath(solFilePath)
        else:
            # Try one of the projects paths
            potentials = []
            for project in self.solutionInfo.projectList:
                proj = self.solutionInfo.projectList[project]
                if proj.includePath is not None:
                    projFilePath = toPosixPath(os.path.join(proj.includePath, includetext))
                    if os.path.isfile(projFilePath):
                        potentials.append(projFilePath)
            
            if len(potentials) == 1:
                return os.path.abspath(potentials[0])
            elif len(potentials) > 1:
                self.config.messagePrinter.error('include text "{0}" in {1} matches multiple files:'.format(includetext, absoluteFilepath))
                formatStr = '  {0} (selected)'
                for p in potentials:
                    self.config.messagePrinter.error(formatStr.format(p))
                    formatStr = '  {0}'
                
                return os.path.abspath(potentials[0])
            
            # Don't know where this file is...
            return None
    
    def AddIncludeTupleToDatabase(self, filepath, solPath, includeTuple, isLocalInclude = True):
        include, lineNumber = includeTuple
        absoluteIncludePath = self.GetIncludeFileAbsolutePath(filepath, include, isLocalInclude)
        
        if not solPath:
            solPath = self.solutionInfo.GetPathRelativeToSolution(filepath)
        
        if absoluteIncludePath:
            solIncPath = self.solutionInfo.GetPathRelativeToSolution(absoluteIncludePath)
            incProject = self.solutionInfo.GetProjectName(absoluteIncludePath)
        else:
            solIncPath = None
            incProject = None
        
        includePath, includeFilename = os.path.split(include)
        
        includeType = self.database.includeTypeSystem
        if isLocalInclude:
            includeType = self.database.includeTypeLocal
        
        fileList = self.database.AddInclude(solPath, include, includeType, includeFilename, incProject, solIncPath, lineNumber)
    
    # PopulateDatabase
    #   This function processes a .h, .c, .hpp, .cpp; file, extracts all of the #include'd file paths,
    #   and places them all into an SQLite database.
    def PopulateDatabase(self):
        # Print helpful info
        self.config.messagePrinter.info("Working directory: {0}".format(os.path.abspath(os.getcwd())))
        self.config.messagePrinter.info("Configuration file: {0}".format(os.path.relpath(self.config.scriptIni)))
        self.config.messagePrinter.info("Source path: {0}".format(os.path.relpath(self.config.sourcePath)))
        
        if not self.isDbOpen:
            self.isDbOpen = self.database.Open()
        
        if not self.isDbOpen:
            self.config.messagePrinter.error("Failed to open database. Exiting!")
            return False
        else:
            self.database.Drop()
            self.database.Create()
        
        # Populate Projects table
        for project in self.solutionInfo.GetProjectList():
            path = self.solutionInfo.GetProjectPath(project)
            level = self.solutionInfo.GetProjectSortOrder(project)
            self.database.AddProject(project, path, level)
            
        # Populate CodeFile and IncludeDirective tables
        processedCounter = 0
        skippedCounter = 0
        startTime = time.clock()
        for root, dirs, files in os.walk(self.solutionInfo.GetSolutionPath(), topdown=True):
            for name in files:
                filepath = os.path.join(root, name)
                
                # Apply the file filter (including only the .cpp, .c, .h and .hpp files presumably)
                # The filter is specified in the .ini file.
                if self.fileFilter and (self.fileFilter.IsIncluded(filepath) and not self.fileFilter.IsExcluded(filepath)):
                    # Get the paths relative to the solution and workout the project folder that
                    # the file is located in.
                    solPath = self.solutionInfo.GetPathRelativeToSolution(filepath)
                    project = self.solutionInfo.GetProjectName(filepath)
                    
                    # Add the file and the includes to the database.
                    if self.isDbOpen:
                        self.database.AddFile(name, project, solPath, exists = True)
                        
                        # Process includes
                        internalIncludes, externalIncludes = self.GetIncludes(filepath)
                        
                        for i in internalIncludes:
                            self.AddIncludeTupleToDatabase(filepath, solPath, i, isLocalInclude = True)
                        
                        for i in externalIncludes:
                            self.AddIncludeTupleToDatabase(filepath, solPath, i, isLocalInclude = False)
                        
                        processedCounter = processedCounter + 1
                    else:
                        self.config.messagePrinter.error("Error, database not open!")
                        return False

                    if processedCounter % 1000 == 0:
                        self.database.SaveProgress() 
                        self.config.messagePrinter.info("Processed {0: >4}, skipped {1: >6} files".format(processedCounter, skippedCounter))
                else:
                    skippedCounter = skippedCounter + 1
                    
        self.database.SaveProgress()
        self.config.messagePrinter.info("Processed {0: >4}, skipped {1: >6} files".format(processedCounter, skippedCounter))
        
        return True
    
    def Close(self):
        self.database.Close()
    
    def DeleteDatabase(self):
        self.database.DeleteFile()
        self.database = None
        
# ################################################################################################ #
# Script Functions                                                                                 #
# ################################################################################################ #
def PrintExampleConfig():
    exampleConfigContents = """; Script options
[Output]
; The special :memory: filename creates an in-memory database that is
; deleted once the script exits. If you want to keep the database
; give it a proper filename but note that it will cost you a slight
; performance hit.
DatabaseFilename:   :memory:
HtmlFilename:       IncludeDependencyMatrix.html

[FileFilter]
IncludePatterns: 
    .*\.cpp$
    .*\.h$ 
    .*\.hpp$ 
    .*\.c$
ExcludePatterns:
    .*moc_.*

; Solution path is relative to the script path
[Paths]
SourceRoot: ./

; The following options are defined using JSON objects. For the JSON format look up
; http://www.json.org/ where you will find the definition of the format.
;
; WARNING!!! There are some additional constraints to the _style_ of JSON you can write here!
;            1. The option name will have NO WHITESPACE before it and the colon ":" will follow
;               immediately after.
;            2. The opening curly brace "{" MUST be on the same line as the option name and MUST
;               have at least one whitespace character between it and the colon.
;            3. You MAY place the JSON string across multiple lines BUT YOU MUST indent ALL of the
;               lines with at least one whitespace character. This includes the closing curly brace.
;
; To make the following example valid, copy it and from each line remove the collon and a single
; space character (i.e. delete the "; " from each line):
; e.g.
; 
; option name: { "path": "Path/To/Project/Relative/To/Solution/",
;  "dependencies" : []
;  }
;
; Note: The JSON object is interpreted in the python script and its members are not optional. Refer
;       to the example INI file that is available in the python script for details.
[JSONObjects]
ProjectGroupsList: {
    "type": "list",
    "object": [
      {
        "type": "group",
        "name": "ProjectGroup1",
        "description": "This is the first example of a project group",
        "projects": [
          {
            "type": "project",
            "name": "FirstProject",
            "path": "Path/To/First/Project/",
            "dependencies": []
          },
          {
            "type": "project",
            "name": "SecondProject",
            "path": "Path/To/Second/Project/",
            "dependencies": [
                "FirstProject"
            ]
          },
          {
            "type": "project",
            "name": "3rdProject",
            "path": "Path/To/3rd/Project/",
            "dependencies": [
                "SecondProject",
                "FirstProject"
            ]
          }
        ]
      }
    ]
  }
"""
    print(exampleConfigContents)

# ################################################################################################ #
# Script Main                                                                                      #
# ################################################################################################ #
def Main(argv):
    # Try and initialise the configuration file
    config = DependencyScriptConfiguration(argv)
    
    if config.printExampleConfig:
        PrintExampleConfig()
    else:
        # Exit if not configured.
        if not config.isConfigured:
            config.messagePrinter.error("Exiting.")
            sys.exit(1)
        
        # Time the execution of our script.
        config.messagePrinter.referenceTime = time.clock()
        
        # Main part of the script. Set the included/excluded files and recurse into the subdirectories.
        fileFilter = FileFilter(config)
        processor = SolutionProcessor(config, fileFilter)
        
        success = processor.PopulateDatabase()
        processor.Close()
        
        if not success:
            return False
        else:
            config.messagePrinter.info("Finished.")
            return True
    
# ################################################################################################ #
# Script Start                                                                                     #
# ################################################################################################ #
if __name__ == "__main__":
    if not Main(sys.argv):
        sys.exit(1)

