configure_file(${CMAKE_CURRENT_SOURCE_DIR}/conf.py.in ${CMAKE_CURRENT_BINARY_DIR}/conf.py @ONLY)

add_custom_command(OUTPUT dnfdragora.8
	COMMAND ${SPHINX_EXECUTABLE} -b man -c ${CMAKE_CURRENT_BINARY_DIR}
		${CMAKE_CURRENT_SOURCE_DIR} ${CMAKE_CURRENT_BINARY_DIR}
	WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
	COMMENT "Building manpages")

add_custom_target(manpages ALL DEPENDS dnfdragora.8)

if(TARGET pofiles)
	add_dependencies(manpages pofiles)
endif(TARGET pofiles)

install(FILES ${CMAKE_CURRENT_BINARY_DIR}/dnfdragora.8 DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/man/man8)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/dnfdragora.yaml.5 DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/man/man5)
