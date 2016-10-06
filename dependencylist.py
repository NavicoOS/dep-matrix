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
import os.path
import posixpath
import re
import string
import time
import sqlite3
from collections import OrderedDict
import json
import dependencydatabase
import argparse
import codecs

config = None
startTime = time.clock()

def GetDependencieTree(database):
    global config
    
    if not database.isOpen:
        database.Open()
    
    if database.isOpen:
        dependencyTree = OrderedDict()
        
        config.messagePrinter.info('Getting dependency tree')
        
        return database.QueryProjectDependencieTree()
    else:
        config.messagePrinter.info('SQLite3 database with filename {0} not found.'.format(database.filename))
    
    return None

def GetDependenciesOfProjectsInSet(dependencyTree, dependencySet):
    global config
    
    # dependencySet is expected as a set
    # dependencySet is expected as a dictionary with string keys and lists of strings as values.
    setSize = len(dependencySet)
    
    newSetItems = set()
    
    if setSize > 0:
        for setItem in dependencySet:
            if setItem in dependencyTree:
                dependencies = dependencyTree[setItem]
                for dependency in dependencies:
                    if dependency not in dependencySet:
                        newSetItems.add(dependency)
    else:
        config.messagePrinter.error('Empty dependency set has no dependencies. Take your illogical logic home!')
    
    return newSetItems

def GetAllProjectDependencies(dependencyTree, targetProject):
    global config
    
    # Seed the set with the desired project.
    dependencySet = set([ targetProject ])
    
    config.messagePrinter.info('Building dependency list for ' + targetProject)
    
    # Iterate over the set of projects and get a set of all the projects that they depend on collectively.
    newDependencySet = GetDependenciesOfProjectsInSet(dependencyTree, dependencySet)
    while len(newDependencySet) > 0:
        # Add the set of the dependencies of the projects already in the set to the set.
        dependencySet = dependencySet | newDependencySet
        newDependencySet = GetDependenciesOfProjectsInSet(dependencyTree, dependencySet)
    
    config.messagePrinter.info('Finished building dependency list for ' + targetProject)
    
    dependencySet.discard(targetProject)
    
    return dependencySet

def PrintExampleDotConfig(dependencySet, config=None, indent=" "):
    print indent, "node [fontcolor=black shape=box style=filled fillcolor=dodgerblue1];"

    if config is not None:
        solInfo = dependencydatabase.SolutionInfo(config)

        nonAlphanumericRegex = re.compile('[^a-zA-Z0-9]')

        if "ProjectGroupsList" in solInfo.jsonObjects:
            for group in solInfo.jsonObjects["ProjectGroupsList"]:
                groupProjectSet = set([p.name for p in group.projects])
                printProjectSet = dependencySet.intersection(groupProjectSet)

                if len(printProjectSet) > 0:
                    subgraphName = nonAlphanumericRegex.sub('', group.name)
                    print indent, "subgraph", subgraphName, "{"
                    print indent, indent, "rank = same;"
                    for proj in printProjectSet:
                        print indent, indent, proj, ";"
                    print indent, "}"


# ################################################################################################ #
# Script Main                                                                                      #
# ################################################################################################ #
def Main(argv):
    # Time the execution of our script.
    global startTime
    global config
    
    startTime = time.clock()
    
    # Try and initialise the configuration file
    argparser = argparse.ArgumentParser(description='Prints a list of dependencies (projects from which files are #included) for the specified project, or a list of known projects.')
    config = dependencydatabase.DependencyScriptConfiguration(argparser=argparser)
    
    config.argparser.add_argument('-r', '--reuse-database', dest='reuseDatabase', action='store_true', default=False, help='Specifies that an existing database is to be used instead of generating one on this run.')
    config.argparser.add_argument('-d', '--direct', dest='directOnly', action='store_true', default=False, help='Only print the direct project dependencies. Otherwise both direct and indirect dependencies are printed.')
    config.argparser.add_argument('-p', '--project-name', dest='projectName', required=True, action='append', metavar='<project-name>', help='The name of the project for which we will generate the dependency list. The \'?\', \'^\' and \'~\' can be used to: list all known projects, list projects that are not depended on by any other project (top level projects) and list all projects that depend on no other project respectively.')
    config.argparser.add_argument('--dot', dest='printDot', action='store_true', default=False, help='Instead of printing the dependencies print a dot graph instead.')
    config.argparser.add_argument('--example-dot-config', dest='exampleDot', action='store_true', default=False, help='Prints an example dot configuration on stdout. Only projects that would have been printed without this option will be included in the configuration.')
    config.argparser.add_argument('--dot-config', dest='dotConfig', metavar='<dot-config-file>', help='The contents of this file will be added to the generated graph output before the edges are specified.')

    config.Configure(argv)
    
    if config.printExampleConfig:
        dependencydatabase.PrintExampleConfig()
    else:
        # Time the execution of our script.
        config.messagePrinter.referenceTime = time.clock()
        
        slnProcessor = None
        database = None
        if config.reuseDatabase and os.path.exists(config.databaseFilename):
            database = dependencydatabase.DependencyScriptDatabase(config.databaseFilename, messagePrinter=config.messagePrinter)
        elif config.isConfigured:
            fileFilter = dependencydatabase.FileFilter(config)
            slnProcessor = dependencydatabase.SolutionProcessor(config, fileFilter)
            if slnProcessor.PopulateDatabase():
                database = slnProcessor.database
            else:
                slnProcessor.database.close()

        if database is not None:
            # Main part of the script. Set the included/excluded files and recurse into the subdirectories.
            dependencieTree = GetDependencieTree(database)

            if dependencieTree is not None:
                dependencySet = set()
                for project in config.projectName:
                    if project == '?':
                        dependencySet = set(dependencieTree.keys())
                    elif project == '^':
                        # Print all top-level projects
                        dependencySet = set(dependencieTree.keys())
                        for proj in dependencieTree:
                            dependencySet -= dependencieTree[proj]
                    elif project == '~':
                        # Print all projects with no dependencies
                        for proj in dependencieTree:
                            if len(dependencieTree[proj]) == 0:
                                dependencySet.add(proj)
                    else:
                        if config.directOnly:
                            try:
                                dependencySet = dependencieTree[project]
                            except:
                                config.messagePrinter.error('Couldn\'t find {0} dependencies. Are you sure the project exists?'.format(project))
                                return False
                        else:
                            dependencySet = GetAllProjectDependencies(dependencieTree, project)

                config.messagePrinter.info('Found {0} dependencies.'.format(str(len(dependencySet))))

                dependencyList = list(dependencySet)
                dependencyList.sort()
                if config.printDot:
                    indent = " "
                    specialNames = { "?": "all_projects", "^": "top_level_projects", "~": "core_building_blocks" }

                    # When we are printing using "dot" we should include the
                    # specified project in our output which we don't do in
                    # our normal mode.
                    projectNames = [p for p in config.projectName if p not in specialNames]
                    dependencyList = projectNames + dependencyList

                    if config.exampleDot:
                        PrintExampleDotConfig(dependencySet, config, indent)
                    else:
                        graphName = "inc_dep"
                        if len(config.projectName) == 1:
                            graphName = specialNames.get(config.projectName[0], config.projectName[0])
                        print "digraph", graphName, "{"
                        if config.dotConfig is not None:
                            with codecs.open(config.dotConfig, 'r') as f:
                                contents = f.read()
                                print contents
                        for project in dependencyList:
                            wasPrinted = False
                            for dependency in dependencieTree[project]:
                                if dependency in dependencyList:
                                    print indent, project, "->", dependency, ";"
                                    wasPrinted = True
                            if not wasPrinted:
                                print indent, project
                        print "}"
                else:
                    for dependency in dependencyList:
                        print(dependency)

            config.messagePrinter.info("Finished.")
            
            return True
        else:
            config.messagePrinter.info("Error! No database or config file provided. Couldn't read or generate database.")
            
            return False
        
# ################################################################################################ #
# Script Start                                                                                     #
# ################################################################################################ #
if __name__ == '__main__':
    if not Main(sys.argv):
        sys.exit(1)

