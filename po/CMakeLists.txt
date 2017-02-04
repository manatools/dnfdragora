# Find all translation-files
file(GLOB PO_FILES "${CMAKE_CURRENT_SOURCE_DIR}/*.po")

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
