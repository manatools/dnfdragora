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

        # TODO add a localized string for any group in "title"
        self._group_info = {
             'All' : { 
                'title' : _("All"), 
                'icon':  'system_section.png'
                },
             'Accessibility' : {
                'title' : _("Accessibility"),
                'icon': 'accessibility_section.png'
                },
             'Archiving' : {
                'title' : _("Archiving"),
                'icon': 'archiving_section.png',
                'Backup' : {
                    'title' : _("Backup"),
                    'icon' : 'backup_section.png'
                    },
                'Cd burning' : {
                    'title' : _("Cd burning"),
                    'icon' : 'cd_burning_section.png'
                    },
                'Compression' : { 
                    'title' : _("Compression"),
                    'icon' : 'compression_section.png'
                    },
                'Other' : {
                    'title' : _("Other"),
                    'icon' : 'other_archiving.png'
                    }
                },
                'Communications' : {
                        'title' : _("Communications"),
                        'icon'  : 'communications_section.png',
                        'Bluetooth': {
                            'title' : _("Bluetooth"),
                            'icon'  : 'communications_bluetooth_section.png',
                            },
                        'Dial-Up'  : {
                            'title' : _("Dial-Up"),
                            'icon'  : 'communications_dialup_section.png',
                            },
                        'Fax'      : {
                            'title' : _("Fax"),
                            'icon'  : 'communications_fax_section.png',
                            },
                        'Mobile'   : {
                            'title' : _("Mobile"),
                            'icon'  : 'communications_mobile_section',
                            },
                        'Radio'    : {
                            'title' : _("Radio"),
                            'icon'  : 'communications_radio_section.png',
                            },
                        'Serial'   : {
                            'title' : _("Serial"),
                            'icon'  : 'communications_serial_section.png',
                            },
                        'Telephony': {
                            'title' : _("Telephony"),
                            'icon'  : 'communications_phone_section',
                            },
                    },
                'Databases' : {
                    'title': _("Databases"),
                    'icon' :'databases_section.png'
                 },
                'Development' : {
                    'title': _("Development"),
                    'icon' : 'development_section.png',
                    'Basic' : {
                        'title' : _("Basic"),
                        },
                    'C' : {
                        'title' : _("C")
                        },
                    'C++' : {
                        'title' : _("C++"),
                        },
                    'C#' : {
                        'title' : _("C#"),
                        #'icon' : ''
                        },
                    'Databases' : {
                        'title' : _("Databases"),
                        'icon' : 'databases_section.png'
                        },
                    'Debug' : {
                        'title' : _("Debug"),
                        #'icon' : ''
                        },
                    'Erlang' : {
                        'title' : _("Erlang"),
                        #'icon' : ''
                        },
                    'GNOME and GTK+' : {
                        'title' : _("GNOME and GTK+"),
                        'icon' : 'gnome_section.png'
                        },
                    'Java' : {
                        'title' : _("Java"),
                        #'icon' : ''
                        },
                    'KDE and Qt' : {
                        'title' : _("KDE and Qt"),
                        'icon' : 'kde_section.png'
                        },
                    'Kernel' : {
                        'title' : _("Kernel"),
                        #'icon' : ''
                        },
                    'OCaml' : {
                        'title' : _("OCaml"),
                        #'icon' : ''
                        },
                    'Other' : {
                        'title' : _("Other"),
                        #'icon' : ''
                        },
                    'Perl' : {
                        'title' : _("Perl"),
                        #'icon' : ''
                        },
                    'PHP' : {
                        'title' : _("PHP"),
                        #'icon' : ''
                        },
                    'Python' : {
                        'title' : _("Python"),
                        #'icon' : ''
                        },
                    'Tools' : {
                        'title' : _("Tools"),
                        'icon' : 'development_tools_section.png',
                        },
                    'X11' : {
                        'title' : _("X11"),
                        #'icon' : ''
                        },
                },
                'Documentation' : {
                    'title' : _("Documentation"),
                    'icon' : 'documentation_section.png'
                },
                'Editors' : {
                    'title' : _("Editors"),
                    'icon' : 'editors_section.png'
                },
                'Education' : {
                    'title' : _("Education"),
                    'icon' : 'education_section.png'
                },
                'Empty' : {
                    'title' : _("Empty"),
                    #'icon' : TODO
                },
                'Emulators' : {
                    'title' : _("Emulators"),
                    'icon' : 'emulators_section.png'
                },
                'File tools' : {
                    'title' : _("File tools"),
                    'icon' : 'file_tools_section.png'
                },
                'Games' : {
                    'title' : _("Games"),
                    'icon' : 'amusement_section.png',
                    'Adventure' : {
                        'title' : _("Adventure"),
                        'icon' : 'adventure_section.png',
                    },
                    'Arcade' : {
                        'title' : _("Arcade"),
                        'icon' : 'arcade_section.png',
                    },
                    'Boards' : {
                        'title' : _("Boards"),
                        'icon' : 'boards_section.png',
                    },
                    'Cards' : {
                        'title' : _("Cards"),
                        'icon' : 'cards_section.png',
                    },
                    'Other' : {
                        'title' : _("Other"),
                        'icon' : 'other_amusement.png',
                    },
                    'Puzzles' : {
                        'title' : _("Puzzles"),
                        'icon' : 'puzzle_section.png',
                    },
                    'Shooter' : {
                        'title' : _("Shooter"),
                        'icon' : 'shooter_section.png',
                    },
                    'Simulation' : {
                        'title' : _("Simulation"),
                        'icon' : 'simulation_section.png',
                    },
                    'Sports' : {
                        'title' : _("Sports"),
                        'icon' : 'sport_section.png',
                    },
                    'Strategy' : {
                        'title' : _("Strategy"),
                        'icon' : 'strategy_section.png',
                    },
                },
                'Geography' : {
                    'title' : _("Geography"),
                    'icon' : 'geography_section.png'
                },
                'Graphical desktop' : {
                    'title' : _("Graphical desktop"),
                    'icon' : 'graphical_desktop_section.png',
                    'Enlightenment' : {
                        'title' : _("Enlightenment"),
                        'icon' : 'enlightment_section.png',
                    },
                    'GNOME' : {
                        'title' : _("GNOME"),
                        'icon' : 'gnome_section.png',
                    },
                    'Icewm' : {
                        'title' : _("Icewm"),
                        'icon' : 'icewm_section.png',
                    },
                    'KDE' : {
                        'title' : _("KDE"),
                        'icon' : 'kde_section.png',
                    },
                    'Other' : {
                        'title' : _("Other"),
                        'icon' : 'more_applications_other_section.png',
                    },
                    'WindowMaker' : {
                        'title' : _("WindowMaker"),
                        'icon' : 'windowmaker_section.png',
                    },
                    'Xfce' : {
                        'title' : _("Xfce"),
                        'icon' : 'xfce_section.png',
                    },
                },
                'Graphics' : {
                    'title' : _("Graphics"),
                    'icon' : 'graphics_section.png',
                    '3D' : {
                        'title' : _("3D"),
                        'icon' : 'graphics_3d_section.png',
                    },
                    'Editors and Converters' : {
                        'title' : _("Editors and Converters"),
                        'icon' : 'graphics_editors_section.png',
                    },
                    'Utilities' : {
                        'title' : _("Utilities"),
                        'icon' : 'graphics_utilities_section.png',
                    },
                    'Photography' : {
                        'title' : _("Photography"),
                        'icon' : 'graphics_photography_section.png',
                    },
                    'Scanning' : {
                        'title' : _("Scanning"),
                        'icon' : 'graphics_scanning_section.png',
                    },
                    'Viewers' : {
                        'title' : _("Viewers"),
                        'icon' : 'graphics_viewers_section.png',
                    },
                },
                'Monitoring' : {
                    'title' : _("Monitoring"),
                    'icon' : 'monitoring_section.png'
                },
                'Networking' : {
                    'title' : _("Networking"),
                    'icon' : 'networking_section.png',
                    'File transfer' : {
                        'title' : _("File transfer"),
                        'icon' : 'file_transfer_section.png',
                    },
                    'IRC' : {
                        'title' : _("IRC"),
                        'icon' : 'irc_section.png',
                    },
                    'Instant messaging' : {
                        'title' : _("Instant messaging"),
                        'icon' : 'instant_messaging_section.png',
                    },
                    'Mail' : {
                        'title' : _("Mail"),
                        'icon' : 'mail_section.png',
                    },
                    'News' : {
                        'title' : _("News"),
                        'icon' : 'news_section.png',
                    },
                    'Other' : {
                        'title' : _("Other"),
                        'icon' : 'other_networking.png',
                    },
                    'Remote access' : {
                        'title' : _("Remote access"),
                        'icon' : 'remote_access_section.png',
                    },
                    'WWW' : {
                        'title' : _("WWW"),
                        'icon' : 'networking_www_section.png',
                    },
                },
                'Office' : {
                    'title' : _("Office"),
                    'icon' : 'office_section.png',
                    'Dictionary' : {
                        'title' : _("Dictionary"),
                        'icon' : 'office_dictionary_section.png',
                    },
                    'Finance' : {
                        'title' : _("Finance"),
                        'icon' : 'finances_section.png',
                    },
                    'Management' : {
                        'title' : _("Management"),
                        'icon' : 'timemanagement_section.png',
                    },
                    'Organizer' : {
                        'title' : _("Organizer"),
                        'icon' : 'timemanagement_section.png',
                    },
                    'Utilities' : {
                        'title' : _("Utilities"),
                        'icon' : 'office_accessories_section.png',
                    },
                    'Spreadsheet' : {
                        'title' : _("Spreadsheet"),
                        'icon' : 'spreadsheet_section.png',
                    },
                    'Suite' : {
                        'title' : _("Suite"),
                        'icon' : 'office_suite.png',
                    },
                    'Word processor' : {
                        'title' : _("Word processor"),
                        'icon' : 'wordprocessor_section.png',
                    },
                },
                'Publishing' : {
                    'title' : _("Publishing"),
                    'icon' : 'publishing_section.png'
                },
                'Sciences' : {
                    'title' : _("Sciences"),
                    'icon' : 'sciences_section.png',
                    'Astronomy' : {
                        'title' : _("Astronomy"),
                        'icon' : 'astronomy_section.png',
                    },
                    'Biology' : {
                        'title' : _("Biology"),
                        'icon' : 'biology_section.png',
                    },
                    'Chemistry' : {
                        'title' : _("Chemistry"),
                        'icon' : 'chemistry_section.png',
                    },
                    'Computer science' : {
                        'title' : _("Computer science"),
                        'icon' : 'computer_science_section.png',
                    },
                    'Geosciences' : {
                        'title' : _("Geosciences"),
                        'icon' : 'geosciences_section.png',
                    },
                    'Mathematics' : {
                        'title' : _("Mathematics"),
                        'icon' : 'mathematics_section.png',
                    },
                    'Other' : {
                        'title' : _("Other"),
                        'icon' : 'other_sciences.png',
                    },
                    'Physics' : {
                        'title' : _("Physics"),
                        'icon' : 'physics_section.png',
                    },
                },
                'Security' : {
                    'title' : _("Security"),
                    'icon' : 'security_section.png'
                },
                'Shells' : {
                    'title' : _("Shells"),
                    'icon' : 'shells_section.png'
                },
                'Sound' : {
                    'title' : _("Sound"),
                    'icon' : 'sound_section.png',
                    'Editors and Converters' : {
                        'title' : _("Editors and Converters"),
                        'icon' : 'sound_editors_section.png',
                    },
                    'Midi' : {
                        'title' : _("Midi"),
                        'icon' : 'sound_midi_section.png',
                    },
                    'Mixers' : {
                        'title' : _("Mixers"),
                        'icon' : 'sound_mixers_section.png',
                    },
                    'Players' : {
                        'title' : _("Players"),
                        'icon' : 'sound_players_section.png',
                    },
                    'Utilities' : {
                        'title' : _("Utilities"),
                        'icon' : 'sound_utilities_section.png',
                    },
                },
                'System' : {
                    'title' : _("System"),
                    'icon' : 'system_section.png',
                    'Base' : {
                        'title' : _("Base"),
                        'icon' : 'system_section.png',
                    },
                    'Boot and Init' : {
                        'title' : _("Boot and Init"),
                        'icon' : 'boot_init_section.png',
                    },
                    'Cluster' : {
                        'title' : _("Cluster"),
                        'icon' : 'parallel_computing_section.png',
                    },
                    'Configuration' : {
                        'title' : _("Configuration"),
                        'icon' : 'configuration_section.png',
                    },
                    'Fonts' : {
                        'title' : _("Fonts"),
                        'icon' : 'chinese_section.png',
                        'True type' : {
                            'title' : _("True type"),
                            #'icon' : '',
                        },
                        'Type1' : {
                            'title' : _("Type1"),
                            #'icon' : '',
                        },
                        'X11 bitmap' : {
                            'title' : _("X11 bitmap"),
                            #'icon' : '',
                        },
                    },
                    'Internationalization' : {
                        'title' : _("Internationalization"),
                        'icon' : 'chinese_section.png',
                    },
                    'Kernel and hardware' : {
                        'title' : _("Kernel and hardware"),
                        'icon' : 'hardware_configuration_section.png',
                    },
                    'Libraries' : {
                        'title' : _("Libraries"),
                        'icon' : 'system_section.png',
                    },
                    'Networking' : {
                        'title' : _("Networking"),
                        'icon' : 'networking_configuration_section.png',
                    },
                    'Packaging' : {
                        'title' : _("Packaging"),
                        'icon' : 'packaging_section.png',
                    },
                    'Printing' : {
                        'title' : _("Printing"),
                        'icon' : 'printing_section.png',
                    },
                    'Servers' : {
                        'title' : _("Servers"),
                        'icon' : 'servers_section.png',
                    },
                    'X11' : {
                        'title' : _("X11"),
                        'icon' : 'x11_section.png',
                    },
                },
                'Terminals' : {
                    'title' : _("Terminals"),
                    'icon' : 'terminals_section.png'
                },
                'Text tools' : {
                    'title' : _("Text tools"),
                    'icon' : 'text_tools_section.png'
                },
                'Toys' : {
                    'title' : _("Toys"),
                    'icon' : 'toys_section.png'
                },
                'Video' : {
                    'title' : _("Video"),
                    'icon' : 'video_section.png',
                    'Editors and Converters' : {
                        'title' : _("Editors and Converters"),
                        'icon' : 'video_editors_section.png',
                    },
                    'Players' : {
                        'title' : _("Players"),
                        'icon' : 'video_players_section.png',
                    },
                    'Television' : {
                        'title' : _("Television"),
                        'icon' : 'video_television_section.png',
                    },
                    'Utilities' : {
                        'title' : _("Utilities"),
                        'icon' : 'video_utilities_section.png',
                    },
                },
                ## for Mageia Choice:
                'Workstation' : {
                    'title' : _("Workstation"),
                    'icon' : 'system_section.png',
                    'Configuration' : {
                        'title' : _("Configuration"),
                        'icon' : 'configuration_section.png',
                    },
                    'Console Tools' : {
                        'title' : _("Console Tools"),
                        'icon' : 'interpreters_section.png',
                    },
                    'Documentation' : {
                        'title' : _("Documentation"),
                        'icon' : 'documentation_section.png',
                    },
                    'Game station' : {
                        'title' : _("Game station"),
                        'icon' : 'amusement_section.png',
                    },
                    'Internet station' : {
                        'title' : _("Internet station"),
                        'icon' : 'networking_section.png',
                    },
                    'Multimedia station' : {
                        'title' : _("Multimedia station"),
                        'icon' : 'multimedia_section.png',
                    },
                    'Network Computer (client)' : {
                        'title' : _("Network Computer (client)"),
                        'icon' : 'other_networking.png',
                    },
                    'Office Workstation' : {
                        'title' : _("Office Workstation"),
                        'icon' : 'office_section.png',
                    },
                    'Scientific Workstation' : {
                        'title' : _("Scientific Workstation"),
                        'icon' : 'sciences_section.png',
                    },
                },
                'Graphical Environment' : {
                    'title' : _("Graphical Environment"),
                    'icon' : 'graphical_desktop_section.png',
                    'GNOME Workstation' : {
                        'title' : _("GNOME Workstation"),
                        'icon' : 'gnome_section.png',
                    },
                    'IceWm Desktop' : {
                        'title' : _("IceWm Desktop"),
                        'icon' : 'icewm_section.png',
                    },
                    'KDE Workstation' : {
                        'title' : _("KDE Workstation"),
                        'icon' : 'kde_section.png',
                    },
                    'Other Graphical Desktops' : {
                        'title' : _("Other Graphical Desktops"),
                        'icon' : 'more_applications_other_section.png',
                    },
                },
                'Development' : {
                    'title' : _("Development"),
                    'icon' : 'development_section.png',
                    'Development' : {
                        'title' : _("Development"),
                        'icon' : 'development_section.png',
                    },
                    'Documentation' : {
                        'title' : _("Documentation"),
                        'icon' : 'documentation_section.png',
                    },
                },
                'Search' : {
                    'title' : _("Search result"),
                    #'icon' : TODO
                },
                'Server' : {
                    'title' : _("Server"),
                    'icon' : 'servers_section.png',
                    'DNS/NIS' : {
                        'title' : _("DNS/NIS"),
                        'icon' : 'networking_section.png',
                    },
                    'Database' : {
                        'title' : _("Database"),
                        'icon' : 'databases_section.png',
                    },
                    'Firewall/Router' : {
                        'title' : _("Firewall/Router"),
                        'icon' : 'networking_section.png',
                    },
                    'Mail' : {
                        'title' : _("Mail"),
                        'icon' : 'mail_section.png',
                    },
                    'Mail/Groupware/News' : {
                        'title' : _("Mail/Groupware/News"),
                        'icon' : 'mail_section.png',
                    },
                     'Network Computer server' : {
                        'title' : _("Network Computer server"),
                        'icon' : 'networking_section.png',
                    },
                     'Web/FTP' : {
                        'title' : _("Web/FTP"),
                        'icon' : 'networking_www_section.png',
                    },
                },
            }


    @property
    def groups(self):
        '''
        return all the group info
        '''
        return self._group_info
    
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
        g = self._group_info
        for k in groups:
            if k in g.keys():
                g = g[k]
            else:
                g = None
                break
        
        if g and 'icon' in g:
            icon_path += g['icon']
        else:
            icon_path += "applications_section.png"
            
        return icon_path

