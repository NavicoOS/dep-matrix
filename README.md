Include Dependency Scripts
==========================

The include dependency scripts are given a desired hierarchy of C/C++ projects and they then process
a given source directory's files for #include directives and compare the actual inclusions
(dependencies) between the different projects with the desired hierarchy.

There are 4 scripts in this directory:
  * dependencydatabase.py
  * dependency2html.py
  * dependencylist.py
  * utility.py

All scripts require python 2.7 to run correctly.

And their functionality is documented below.


dependencydatabase.py
---------------------

This script processes a source directory and generates an SQLite3 database with all of the different
#include directives that it had found.

This database also contains the specified project hierarchy and each file processed is associated
with its project (if known) according to the project's system path. Similarly, all the #include
directives that are found in a file are processed and associated with a project if the #include-d
file exists in that projects directory.

The database schema can be found inside of the script itself. You should refer to the script for the
most up-to-date schema information.

The script requires a configuration INI file which specifies the source directory, included and
excluded file patterns and the list of known projects. The script itself contains an example config
file which it can print on the command line:

    python dependencydatabase.py --print-example-config

See help for details

    python dependencydatabase.py --help


dependency2html.py
------------------

This script generates an HTML report containing a dependency matrix for all the projects specified
in its INI file (which is shared and has the same format).

The INI file's projects can also have their colour modified by adding the:

    "css" : {
        "background-color": "#99CCFF"
    },

setting.

The output of the script is an HTML file with a filename specified in the INI file.

See

    python dependency2html.py --help

for details.

dependencylist.py
-----------------

This script is intended to be used by other scripts, and generates a simple list of actual
dependencies that a particular project has. It does this by using the dependencydatabase.py script
to either generate an inmemory database, a file database or it can also use an existing database to
generate its report.

See

    python dependencylist.py --help

for details.


utility.py
----------

This script contains a bunch misc. utilities that the other scripts share and use but don't own.
Currently it only contains a Logger which standardises the way the the scripts print info, debug and
error messages.

License
=======

These scripts are provided under the conditions of the Apache 2.0 license.

Copyright 2016 Lazar Sumar, Navico

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
