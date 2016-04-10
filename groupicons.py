
class GroupIcons:
    '''
    This class manages the access to group name and icons
    '''
    def __init__(self, icon_path=None):

        if icon_path:
            self.icon_path = icon_path if icon_path.endswith('/') else icon_path + "/"
            self.mini_icon_path = self.icon_path + "mini/"
        else:
            self.icon_path = '/usr/share/icons/'
            self.mini_icon_path = '/usr/share/icons/mini/'

        # TODO add a localized string for any group
        self.group = {
             'All' : { 
                'title' : "All", 
                'icon':  'system_section.png'
                },
             'Accessibility' : {
                'title' : "Accessibility",
                'icon': 'accessibility_section.png'
                },
             'Archiving' : {
                'title' : "Archiving",
                'icon': 'archiving_section.png',
                'Backup' : {
                    'title' : "Backup",
                    'icon' : 'backup_section.png'
                    },
                'Cd burning' : {
                    'title' : "Cd burning",
                    'icon' : 'cd_burning_section.png'
                    },
                'Compression' : { 
                    'title' : "Compression",
                    'icon' : 'compression_section.png'
                    },
                'Other' : {
                    'title' : "Other",
                    'icon' : 'other_archiving.png'
                    }
                },
                'Communications' : {
                        'title' : "Communications",
                        'icon'  : 'communications_section.png',
                        'Bluetooth': {
                            'title' : "Bluetooth",
                            'icon'  : 'communications_bluetooth_section.png',
                            },
                        'Dial-Up'  : {
                            'title' : "Dial-Up",
                            'icon'  : 'communications_dialup_section.png',
                            },
                        'Fax'      : {
                            'title' : "Fax",
                            'icon'  : 'communications_fax_section.png',
                            },
                        'Mobile'   : {
                            'title' : "Mobile",
                            'icon'  : 'communications_mobile_section',
                            },
                        'Radio'    : {
                            'title' : "Radio",
                            'icon'  : 'communications_radio_section.png',
                            },
                        'Serial'   : {
                            'title' : "Serial",
                            'icon'  : 'communications_serial_section.png',
                            },
                        'Telephony': {
                            'title' : "Telephony",
                            'icon'  : 'communications_phone_section',
                            },
                    },
                'Databases' : {
                    'title': "Databases",
                    'icon' :'databases_section.png'
                 },
                'Development' : {
                    'title': "Development",
                    'icon' : 'development_section.png',
                    'Basic' : {
                        'title' : "Basic",
                        },
                    'C' : {
                        'title' : "C"
                        },
                    'C++' : {
                        'title' : "C++",
                        },
                    'C#' : {
                        'title' : "C#",
                        #'icon' : ''
                        },
                    'Databases' : {
                        'title' : "Databases",
                        'icon' : 'databases_section.png'
                        },
                    'Debug' : {
                        'title' : "Debug",
                        #'icon' : ''
                        },
                    'Erlang' : {
                        'title' : "Erlang",
                        #'icon' : ''
                        },
                    'GNOME and GTK+' : {
                        'title' : "GNOME and GTK+",
                        'icon' : 'gnome_section.png'
                        },
                    'Java' : {
                        'title' : "Java",
                        #'icon' : ''
                        },
                    'KDE and Qt' : {
                        'title' : "KDE and Qt",
                        'icon' : 'kde_section.png'
                        },
                    'Kernel' : {
                        'title' : "Kernel",
                        #'icon' : ''
                        },
                    'OCaml' : {
                        'title' : "OCaml",
                        #'icon' : ''
                        },
                    'Other' : {
                        'title' : "Other",
                        #'icon' : ''
                        },
                    'Perl' : {
                        'title' : "Perl",
                        #'icon' : ''
                        },
                    'PHP' : {
                        'title' : "PHP",
                        #'icon' : ''
                        },
                    'Python' : {
                        'title' : "Python",
                        #'icon' : ''
                        },
                    'Tools' : {
                        'title' : "Tools",
                        'icon' : 'development_tools_section.png',
                        },
                    'X11' : {
                        'title' : "X11",
                        #'icon' : ''
                        },
                },
                'Documentation' : {
                    'title' : "Documentation",
                    'icon' : 'documentation_section.png'
                },
                'Editors' : {
                    'title' : "Editors",
                    'icon' : 'editors_section.png'
                },
                'Education' : {
                    'title' : "Education",
                    'icon' : 'education_section.png'
                },
                'Emulators' : {
                    'title' : "Emulators",
                    'icon' : 'emulators_section.png'
                },
                'File tools' : {
                    'title' : "File tools",
                    'icon' : 'file_tools_section.png'
                },
                'Games' : {
                    'title' : "Games",
                    'icon' : 'amusement_section.png',
                    'Adventure' : {
                        'title' : "Adventure",
                        'icon' : 'adventure_section.png',
                    },
                    'Arcade' : {
                        'title' : "Arcade",
                        'icon' : 'arcade_section.png',
                    },
                    'Boards' : {
                        'title' : "Boards",
                        'icon' : 'boards_section.png',
                    },
                    'Cards' : {
                        'title' : "Cards",
                        'icon' : 'cards_section.png',
                    },
                    'Other' : {
                        'title' : "Other",
                        'icon' : 'other_amusement.png',
                    },
                    'Puzzles' : {
                        'title' : "Puzzles",
                        'icon' : 'puzzle_section.png',
                    },
                    'Shooter' : {
                        'title' : "Shooter",
                        'icon' : 'shooter_section.png',
                    },
                    'Simulation' : {
                        'title' : "Simulation",
                        'icon' : 'simulation_section.png',
                    },
                    'Sports' : {
                        'title' : "Sports",
                        'icon' : 'sport_section.png',
                    },
                    'Strategy' : {
                        'title' : "Strategy",
                        'icon' : 'strategy_section.png',
                    },
                },
                'Geography' : {
                    'title' : "Geography",
                    'icon' : 'geography_section.png'
                },
                'Graphical desktop' : {
                    'title' : "Graphical desktop",
                    'icon' : 'graphical_desktop_section.png',
                    'Enlightenment' : {
                        'title' : "Enlightenment",
                        'icon' : 'enlightment_section.png',
                    },
                    'GNOME' : {
                        'title' : "GNOME",
                        'icon' : 'gnome_section.png',
                    },
                    'Icewm' : {
                        'title' : "Icewm",
                        'icon' : 'icewm_section.png',
                    },
                    'KDE' : {
                        'title' : "KDE",
                        'icon' : 'kde_section.png',
                    },
                    'Other' : {
                        'title' : "Other",
                        'icon' : 'more_applications_other_section.png',
                    },
                    'WindowMaker' : {
                        'title' : "WindowMaker",
                        'icon' : 'windowmaker_section.png',
                    },
                    'Xfce' : {
                        'title' : "Xfce",
                        'icon' : 'xfce_section.png',
                    },
                },
                'Graphics' : {
                    'title' : "Graphics",
                    'icon' : 'graphics_section.png',
                    '3D' : {
                        'title' : "3D",
                        'icon' : 'graphics_3d_section.png',
                    },
                    'Editors and Converters' : {
                        'title' : "Editors and Converters",
                        'icon' : 'graphics_editors_section.png',
                    },
                    'Utilities' : {
                        'title' : "Utilities",
                        'icon' : 'graphics_utilities_section.png',
                    },
                    'Photography' : {
                        'title' : "Photography",
                        'icon' : 'graphics_photography_section.png',
                    },
                    'Scanning' : {
                        'title' : "Scanning",
                        'icon' : 'graphics_scanning_section.png',
                    },
                    'Viewers' : {
                        'title' : "Viewers",
                        'icon' : 'graphics_viewers_section.png',
                    },
                },
                'Monitoring' : {
                    'title' : "Monitoring",
                    'icon' : 'monitoring_section.png'
                },
                'Networking' : {
                    'title' : "Networking",
                    'icon' : 'networking_section.png',
                    'File transfer' : {
                        'title' : "File transfer",
                        'icon' : 'file_transfer_section.png',
                    },
                    'IRC' : {
                        'title' : "IRC",
                        'icon' : 'irc_section.png',
                    },
                    'Instant messaging' : {
                        'title' : "Instant messaging",
                        'icon' : 'instant_messaging_section.png',
                    },
                    'Mail' : {
                        'title' : "Mail",
                        'icon' : 'mail_section.png',
                    },
                    'News' : {
                        'title' : "News",
                        'icon' : 'news_section.png',
                    },
                    'Other' : {
                        'title' : "Other",
                        'icon' : 'other_networking.png',
                    },
                    'Remote access' : {
                        'title' : "Remote access",
                        'icon' : 'remote_access_section.png',
                    },
                    'WWW' : {
                        'title' : "WWW",
                        'icon' : 'networking_www_section.png',
                    },
                },
                'Office' : {
                    'title' : "Office",
                    'icon' : 'office_section.png',
                    'Dictionary' : {
                        'title' : "Dictionary",
                        'icon' : 'office_dictionary_section.png',
                    },
                    'Finance' : {
                        'title' : "Finance",
                        'icon' : 'finances_section.png',
                    },
                    'Management' : {
                        'title' : "Management",
                        'icon' : 'timemanagement_section.png',
                    },
                    'Organizer' : {
                        'title' : "Organizer",
                        'icon' : 'timemanagement_section.png',
                    },
                    'Utilities' : {
                        'title' : "Utilities",
                        'icon' : 'office_accessories_section.png',
                    },
                    'Spreadsheet' : {
                        'title' : "Spreadsheet",
                        'icon' : 'spreadsheet_section.png',
                    },
                    'Suite' : {
                        'title' : "Suite",
                        'icon' : 'office_suite.png',
                    },
                    'Word processor' : {
                        'title' : "Word processor",
                        'icon' : 'wordprocessor_section.png',
                    },
                },
                'Publishing' : {
                    'title' : "Publishing",
                    'icon' : 'publishing_section.png'
                },
                'Sciences' : {
                    'title' : "Sciences",
                    'icon' : 'sciences_section.png',
                    'Astronomy' : {
                        'title' : "Astronomy",
                        'icon' : 'astronomy_section.png',
                    },
                    'Biology' : {
                        'title' : "Biology",
                        'icon' : 'biology_section.png',
                    },
                    'Chemistry' : {
                        'title' : "Chemistry",
                        'icon' : 'chemistry_section.png',
                    },
                    'Computer science' : {
                        'title' : "Computer science",
                        'icon' : 'computer_science_section.png',
                    },
                    'Geosciences' : {
                        'title' : "Geosciences",
                        'icon' : 'geosciences_section.png',
                    },
                    'Mathematics' : {
                        'title' : "Mathematics",
                        'icon' : 'mathematics_section.png',
                    },
                    'Other' : {
                        'title' : "Other",
                        'icon' : 'other_sciences.png',
                    },
                    'Physics' : {
                        'title' : "Physics",
                        'icon' : 'physics_section.png',
                    },
                },
                'Security' : {
                    'title' : "Security",
                    'icon' : 'security_section.png'
                },
                'Shells' : {
                    'title' : "Shells",
                    'icon' : 'shells_section.png'
                },
                'Sound' : {
                    'title' : "Sound",
                    'icon' : 'sound_section.png',
                    'Editors and Converters' : {
                        'title' : "Editors and Converters",
                        'icon' : 'sound_editors_section.png',
                    },
                    'Midi' : {
                        'title' : "Midi",
                        'icon' : 'sound_midi_section.png',
                    },
                    'Mixers' : {
                        'title' : "Mixers",
                        'icon' : 'sound_mixers_section.png',
                    },
                    'Players' : {
                        'title' : "Players",
                        'icon' : 'sound_players_section.png',
                    },
                    'Utilities' : {
                        'title' : "Utilities",
                        'icon' : 'sound_utilities_section.png',
                    },
                },
                'System' : {
                    'title' : "System",
                    'icon' : 'system_section.png',
                    'Base' : {
                        'title' : "Base",
                        'icon' : 'system_section.png',
                    },
                    'Boot and Init' : {
                        'title' : "Boot and Init",
                        'icon' : 'boot_init_section.png',
                    },
                    'Cluster' : {
                        'title' : "Cluster",
                        'icon' : 'parallel_computing_section.png',
                    },
                    'Configuration' : {
                        'title' : "Configuration",
                        'icon' : 'configuration_section.png',
                    },
                    'Fonts' : {
                        'title' : "Fonts",
                        'icon' : 'chinese_section.png',
                        'True type' : {
                            'title' : "True type",
                            #'icon' : '',
                        },
                        'Type1' : {
                            'title' : "Type1",
                            #'icon' : '',
                        },
                        'X11 bitmap' : {
                            'title' : "X11 bitmap",
                            #'icon' : '',
                        },
                    },
                    'Internationalization' : {
                        'title' : "Internationalization",
                        'icon' : 'chinese_section.png',
                    },
                    'Kernel and hardware' : {
                        'title' : "Kernel and hardware",
                        'icon' : 'hardware_configuration_section.png',
                    },
                    'Libraries' : {
                        'title' : "Libraries",
                        'icon' : 'system_section.png',
                    },
                    'Networking' : {
                        'title' : "Networking",
                        'icon' : 'networking_configuration_section.png',
                    },
                    'Packaging' : {
                        'title' : "Packaging",
                        'icon' : 'packaging_section.png',
                    },
                    'Printing' : {
                        'title' : "Printing",
                        'icon' : 'printing_section.png',
                    },
                    'Servers' : {
                        'title' : "Servers",
                        'icon' : 'servers_section.png',
                    },
                    'X11' : {
                        'title' : "X11",
                        'icon' : 'x11_section.png',
                    },
                },
                'Terminals' : {
                    'title' : "Terminals",
                    'icon' : 'terminals_section.png'
                },
                'Text tools' : {
                    'title' : "Text tools",
                    'icon' : 'text_tools_section.png'
                },
                'Toys' : {
                    'title' : "Toys",
                    'icon' : 'toys_section.png'
                },
                'Video' : {
                    'title' : "Video",
                    'icon' : 'video_section.png',
                    'Editors and Converters' : {
                        'title' : "Editors and Converters",
                        'icon' : 'video_editors_section.png',
                    },
                    'Players' : {
                        'title' : "Players",
                        'icon' : 'video_players_section.png',
                    },
                    'Television' : {
                        'title' : "Television",
                        'icon' : 'video_television_section.png',
                    },
                    'Utilities' : {
                        'title' : "Utilities",
                        'icon' : 'video_utilities_section.png',
                    },
                },
                ## for Mageia Choice:
                'Workstation' : {
                    'title' : "Workstation",
                    'icon' : 'system_section.png',
                    'Configuration' : {
                        'title' : "Configuration",
                        'icon' : 'configuration_section.png',
                    },
                    'Console Tools' : {
                        'title' : "Console Tools",
                        'icon' : 'interpreters_section.png',
                    },
                    'Documentation' : {
                        'title' : "Documentation",
                        'icon' : 'documentation_section.png',
                    },
                    'Game station' : {
                        'title' : "Game station",
                        'icon' : 'amusement_section.png',
                    },
                    'Internet station' : {
                        'title' : "Internet station",
                        'icon' : 'networking_section.png',
                    },
                    'Multimedia station' : {
                        'title' : "Multimedia station",
                        'icon' : 'multimedia_section.png',
                    },
                    'Network Computer (client)' : {
                        'title' : "Network Computer (client)",
                        'icon' : 'other_networking.png',
                    },
                    'Office Workstation' : {
                        'title' : "Office Workstation",
                        'icon' : 'office_section.png',
                    },
                    'Scientific Workstation' : {
                        'title' : "Scientific Workstation",
                        'icon' : 'sciences_section.png',
                    },
                },
                'Graphical Environment' : {
                    'title' : "Graphical Environment",
                    'icon' : 'graphical_desktop_section.png',
                    'GNOME Workstation' : {
                        'title' : "GNOME Workstation",
                        'icon' : 'gnome_section.png',
                    },
                    'IceWm Desktop' : {
                        'title' : "IceWm Desktop",
                        'icon' : 'icewm_section.png',
                    },
                    'KDE Workstation' : {
                        'title' : "KDE Workstation",
                        'icon' : 'kde_section.png',
                    },
                    'Other Graphical Desktops' : {
                        'title' : "Other Graphical Desktops",
                        'icon' : 'more_applications_other_section.png',
                    },
                },
                'Development' : {
                    'title' : "Development",
                    'icon' : 'development_section.png',
                    'Development' : {
                        'title' : "Development",
                        'icon' : 'development_section.png',
                    },
                    'Documentation' : {
                        'title' : "Documentation",
                        'icon' : 'documentation_section.png',
                    },
                },
                'Server' : {
                    'title' : "Server",
                    'icon' : 'servers_section.png',
                    'DNS/NIS' : {
                        'title' : "DNS/NIS",
                        'icon' : 'networking_section.png',
                    },
                    'Database' : {
                        'title' : "Database",
                        'icon' : 'databases_section.png',
                    },
                    'Firewall/Router' : {
                        'title' : "Firewall/Router",
                        'icon' : 'networking_section.png',
                    },
                    'Mail' : {
                        'title' : "Mail",
                        'icon' : 'mail_section.png',
                    },
                    'Mail/Groupware/News' : {
                        'title' : "Mail/Groupware/News",
                        'icon' : 'mail_section.png',
                    },
                     'Network Computer server' : {
                        'title' : "Network Computer server",
                        'icon' : 'networking_section.png',
                    },
                     'Web/FTP' : {
                        'title' : "Web/FTP",
                        'icon' : 'networking_www_section.png',
                    },
                },
            }

    def groups(self):
        '''
        return all the group info
        '''
        return self.group
    
    def _group(self, k, group_dic) :
        if k in group_dic:
            return group_dic[k]
        return None
    
    def icon(self, group, separator='/') :
        '''
        from the given group as a pathname return the related icon
        if icon_path is passed to the constructor, icon_path/ and icon_path/mini
        are used to return icon_name
        '''
       
        groups = group.split(separator)
        icon_path =  self.mini_icon_path if len(groups) > 1 else self.icon_path
        g = self.group
        for k in groups:
            if k in g:
                g = g[k]
            else:
                g = None
                break
        
        if g and 'icon' in g:
            icon_path += g['icon']
        else:
            icon_path += "applications_section.png"
            
        return icon_path

