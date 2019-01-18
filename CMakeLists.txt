if(POLICY CMP0048)
	cmake_policy(SET CMP0048 NEW)
endif(POLICY CMP0048)

project(dnfdragora VERSION 1.1.1 LANGUAGES NONE)
cmake_minimum_required(VERSION 3.4)

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake")

find_package(PythonInterp 3.4 REQUIRED)
find_package(Gettext)
find_program(SPHINX_EXECUTABLE
	NAMES	sphinx-build-${PYTHON_VERSION_MAJOR}.${PYTHON_VERSION_MINOR}
		sphinx-build-${PYTHON_VERSION_MAJOR}
		sphinx-build)
if(SPHINX_EXECUTABLE STREQUAL "SPHINX_EXECUTABLE-NOTFOUND")
	message(STATUS "Could NOT find sphinx-build.")
else(SPHINX_EXECUTABLE STREQUAL "SPHINX_EXECUTABLE-NOTFOUND")
	message(STATUS "Found sphinx-build: ${SPHINX_EXECUTABLE}")
endif(SPHINX_EXECUTABLE STREQUAL "SPHINX_EXECUTABLE-NOTFOUND")

execute_process(COMMAND ${PYTHON_EXECUTABLE} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib(), end='')" OUTPUT_VARIABLE PYTHON_INSTALL_DIR)
string(REGEX REPLACE "\n$" "" ${PYTHON_INSTALL_DIR} "${PYTHON_INSTALL_DIR}")
execute_process(COMMAND ${PYTHON_EXECUTABLE} -c "import sys; sys.stdout.write('%s.%s' % (sys.version_info.major, sys.version_info.minor))" OUTPUT_VARIABLE PYTHON_MAJOR_DOT_MINOR_VERSION)
message(STATUS "Python install dir is ${PYTHON_INSTALL_DIR}")

option(CHECK_RUNTIME_DEPENDENCIES "Verify the presence of runtime-only dependencies?" ON)

if(CHECK_RUNTIME_DEPENDENCIES)
	include(FindPythonModule)

	# Find the dnfdaemon module
	find_python_module(dnfdaemon REQUIRED)

	# Find yui module
	find_python_module(yui REQUIRED)

	# Find yaml module
	find_python_module(yaml REQUIRED)

	# Find notify2 module
	find_python_module(notify2 REQUIRED)

	# Find xdg module
	find_python_module(xdg REQUIRED)

	# Find cairosvg module
	find_python_module(cairosvg REQUIRED)

	# Find PIL module
	find_python_module(PIL REQUIRED)

	# Find pystray module
	find_python_module(pystray REQUIRED)

endif(CHECK_RUNTIME_DEPENDENCIES)

option(ENABLE_COMPS "Use comps data for organizing packages?" OFF)

# Set the substitution variable accordingly
if(ENABLE_COMPS)
	set(USE_COMPS "True")
else(ENABLE_COMPS)
	set(USE_COMPS "False")
endif(ENABLE_COMPS)

# Set install dirs.
set(CMAKE_INSTALL_BINDIR "${CMAKE_INSTALL_PREFIX}/bin")
set(CMAKE_INSTALL_DATAROOTDIR "${CMAKE_INSTALL_PREFIX}/share")
set(CMAKE_INSTALL_LOCALEDIR "${CMAKE_INSTALL_DATAROOTDIR}/locale")
set(CMAKE_INSTALL_FULL_SYSCONFDIR "/etc" CACHE PATH "sysconfig directory (default /etc)")

# Configure files
configure_file(${CMAKE_SOURCE_DIR}/etc/dnfdragora.yaml.in ${CMAKE_BINARY_DIR}/etc/dnfdragora.yaml @ONLY)
configure_file(${CMAKE_SOURCE_DIR}/dnfdragora/version.py.in ${CMAKE_BINARY_DIR}/dnfdragora/version.py @ONLY)

# Build and install translations
if(GETTEXT_FOUND)
	add_subdirectory(po)
endif(GETTEXT_FOUND)

# Build and install the man-pages
if(NOT SPHINX_EXECUTABLE STREQUAL "SPHINX_EXECUTABLE-NOTFOUND")
	add_subdirectory(man)
endif(NOT SPHINX_EXECUTABLE STREQUAL "SPHINX_EXECUTABLE-NOTFOUND")

# Installing application code
install(PROGRAMS ${CMAKE_SOURCE_DIR}/bin/dnfdragora DESTINATION ${CMAKE_INSTALL_BINDIR})
install(PROGRAMS ${CMAKE_SOURCE_DIR}/bin/dnfdragora-updater DESTINATION ${CMAKE_INSTALL_BINDIR})
file(GLOB_RECURSE PY_SRC LIST_DIRECTORIES false RELATIVE ${CMAKE_SOURCE_DIR} dnfdragora/*.py)
install(FILES ${PY_SRC} ${CMAKE_BINARY_DIR}/dnfdragora/version.py DESTINATION ${PYTHON_INSTALL_DIR}/dnfdragora)

# Installing configuration
install(FILES ${CMAKE_BINARY_DIR}/etc/dnfdragora.yaml DESTINATION ${CMAKE_INSTALL_FULL_SYSCONFDIR}/dnfdragora)
install(FILES ${CMAKE_SOURCE_DIR}/share/applications/org.mageia.dnfdragora-updater.desktop DESTINATION ${CMAKE_INSTALL_FULL_SYSCONFDIR}/xdg/autostart)

# Installing data files
if(GETTEXT_FOUND)
	install(FILES ${CMAKE_BINARY_DIR}/share/metainfo/org.mageia.dnfdragora.appdata.xml DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/appdata)
else()
	install(FILES ${CMAKE_SOURCE_DIR}/share/metainfo/org.mageia.dnfdragora.appdata.xml DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/appdata)
endif(GETTEXT_FOUND)

install(FILES ${CMAKE_SOURCE_DIR}/share/applications/org.mageia.dnfdragora.desktop DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications)
install(FILES ${CMAKE_SOURCE_DIR}/share/applications/org.mageia.dnfdragora-updater.desktop DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications)
install(FILES ${CMAKE_SOURCE_DIR}/share/applications/org.mageia.dnfdragora-localinstall.desktop DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/applications)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/16x16/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/16x16/apps RENAME dnfdragora.png)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/32x32/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/32x32/apps RENAME dnfdragora.png)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/48x48/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/48x48/apps RENAME dnfdragora.png)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/64x64/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/64x64/apps RENAME dnfdragora.png)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/128x128/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/128x128/apps RENAME dnfdragora.png)
install(FILES ${CMAKE_SOURCE_DIR}/share/images/256x256/dnfdragora-logo.png DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/icons/hicolor/256x256/apps RENAME dnfdragora.png)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/share/images DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/dnfdragora)
