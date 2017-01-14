project(dnfdragora NONE)
cmake_minimum_required(VERSION 3.4)

include(FindPkgConfig)
include(GNUInstallDirs)

find_package(PythonInterp 3.4 REQUIRED)

execute_process(COMMAND ${PYTHON_EXECUTABLE} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())" OUTPUT_VARIABLE PYTHON_INSTALL_DIR)
string(STRIP "${PYTHON_INSTALL_DIR}" ${PYTHON_INSTALL_DIR})
execute_process(COMMAND ${PYTHON_EXECUTABLE} -c "import sys; sys.stdout.write('%s.%s' % (sys.version_info.major, sys.version_info.minor))" OUTPUT_VARIABLE PYTHON_MAJOR_DOT_MINOR_VERSION)
message(STATUS "Python install dir is ${PYTHON_INSTALL_DIR}")

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake")

include(FindPythonModule)

# Find the dnfdaemon client module
find_python_module(dnfdaemon.client REQUIRED)

# Find yui module
find_python_module(yui REQUIRED)

# Find yaml module
find_python_module(yaml REQUIRED)

option(ENABLE_COMPS "Use comps data for organizing packages?" OFF)

# Set the substitution variable accordingly
if(ENABLE_COMPS)
	set(USE_COMPS "True")
else(ENABLE_COMPS)
	set(USE_COMPS "False")
endif(ENABLE_COMPS)

# Configure files
configure_file(${CMAKE_SOURCE_DIR}/etc/dnfdragora.yaml.in ${CMAKE_BINARY_DIR}/etc/dnfdragora.yaml @ONLY)

# Installing application code
install(PROGRAMS ${CMAKE_SOURCE_DIR}/bin/dnfdragora DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY ${CMAKE_SOURCE_DIR}/dnfdragora DESTINATION ${PYTHON_INSTALL_DIR})

# Installing configuration
install(FILES ${CMAKE_BINARY_DIR}/etc/dnfdragora.yaml DESTINATION ${CMAKE_INSTALL_FULL_SYSCONFDIR}/dnfdragora)

# Installing data files
install(FILES ${CMAKE_SOURCE_DIR}/share/metainfo/org.mageia.dnfdragora.appdata.xml DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/appdata)
install(FILES ${CMAKE_SOURCE_DIR}/share/applications/org.mageia.dnfdragora.desktop DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/48x48/apps RENAME dnfdragora.png)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/share/images DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/dnfdragora)
