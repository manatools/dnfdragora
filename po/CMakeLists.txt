# Find all translation-files
file(GLOB PO_FILES "${CMAKE_CURRENT_SOURCE_DIR}/*.po")

# Set our target for AppData file
set(xml_file ${CMAKE_BINARY_DIR}/share/metainfo/org.mageia.dnfdragora.appdata.xml)
# Merge the translations into the initial AppData file
add_custom_command(OUTPUT ${xml_file}
        COMMAND ${GETTEXT_MSGFMT_EXECUTABLE} --xml -d ${CMAKE_CURRENT_SOURCE_DIR} --template ${CMAKE_SOURCE_DIR}/share/metainfo/org.mageia.dnfdragora.appdata.xml -o ${xml_file}
        COMMENT "Generating ${xml_file}"
        )
add_custom_target(make_directory_for_xml ALL
    COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_BINARY_DIR}/share/metainfo)
add_custom_target(xml_translations ALL DEPENDS ${xml_file})

# Generate and install each translation in a separate target
foreach(PO_FILE ${PO_FILES})
	string(REPLACE "${CMAKE_CURRENT_SOURCE_DIR}/" "" LANG_NAME "${PO_FILE}")
	string(REPLACE ".po" "" LANG_NAME "${LANG_NAME}")
	gettext_process_po_files("${LANG_NAME}" ALL PO_FILES "${PO_FILE}")
	install(FILES "${CMAKE_CURRENT_BINARY_DIR}/${LANG_NAME}.gmo"
		DESTINATION "${CMAKE_INSTALL_LOCALEDIR}/${LANG_NAME}/LC_MESSAGES/"
		RENAME "dnfdragora.mo"
	)
endforeach(PO_FILE ${PO_FILES})
