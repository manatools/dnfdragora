
class GroupIcons:
    '''
    This class manages the access to group name and icons
    '''
    def __init__(self):
        
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
        '''
       
        groups = group.split(separator)
        icon_path =  '/usr/share/icons/mini/' if len(groups) > 1 else '/usr/share/icons/'
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


#my %group_icons = (

	
	
	#$loc->N("Documentation") => 'documentation_section',
	#$loc->N("Editors") => 'editors_section',
	#$loc->N("Education") => 'education_section',
	#$loc->N("Emulators") => 'emulators_section',
	#$loc->N("File tools") => 'file_tools_section',
	#$loc->N("Games") => 'amusement_section',
	#join('|', $loc->N("Games"), $loc->N("Adventure")) => 'adventure_section',
	#join('|', $loc->N("Games"), $loc->N("Arcade")) => 'arcade_section',
	#join('|', $loc->N("Games"), $loc->N("Boards")) => 'boards_section',
	#join('|', $loc->N("Games"), $loc->N("Cards")) => 'cards_section',
	#join('|', $loc->N("Games"), $loc->N("Other")) => 'other_amusement',
	#join('|', $loc->N("Games"), $loc->N("Puzzles")) => 'puzzle_section',
	#join('|', $loc->N("Games"), $loc->N("Shooter")) => 'shooter_section',
	#join('|', $loc->N("Games"), $loc->N("Simulation")) => 'simulation_section',
	#join('|', $loc->N("Games"), $loc->N("Sports")) => 'sport_section',
	#join('|', $loc->N("Games"), $loc->N("Strategy")) => 'strategy_section',
	#$loc->N("Geography") => 'geography_section',
	#$loc->N("Graphical desktop") => 'graphical_desktop_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("Enlightenment")) => 'enlightment_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("GNOME")) => 'gnome_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("Icewm")) => 'icewm_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("KDE")) => 'kde_section',
	#join('|', $loc->N("Graphical desktop"), $loc->N("Other")) => 'more_applications_other_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("WindowMaker")) => 'windowmaker_section',
	#join('|', $loc->N("Graphical desktop"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("Xfce")) => 'xfce_section',
	#$loc->N("Graphics") => 'graphics_section',
	#join('|', $loc->N("Graphics"), $loc->N("3D")) => 'graphics_3d_section',
	#join('|', $loc->N("Graphics"), $loc->N("Editors and Converters")) => 'graphics_editors_section',
	#join('|', $loc->N("Graphics"), $loc->N("Utilities")) => 'graphics_utilities_section',
	#join('|', $loc->N("Graphics"), $loc->N("Photography")) => 'graphics_photography_section',
	#join('|', $loc->N("Graphics"), $loc->N("Scanning")) => 'graphics_scanning_section',
	#join('|', $loc->N("Graphics"), $loc->N("Viewers")) => 'graphics_viewers_section',
	#$loc->N("Monitoring") => 'monitoring_section',
	#$loc->N("Networking") => 'networking_section',
	#join('|', $loc->N("Networking"), $loc->N("File transfer")) => 'file_transfer_section',
	#join('|', $loc->N("Networking"), $loc->N("IRC")) => 'irc_section',
	#join('|', $loc->N("Networking"), $loc->N("Instant messaging")) => 'instant_messaging_section',
	#join('|', $loc->N("Networking"), $loc->N("Mail")) => 'mail_section',
	#join('|', $loc->N("Networking"), $loc->N("News")) => 'news_section',
	#join('|', $loc->N("Networking"), $loc->N("Other")) => 'other_networking',
	#join('|', $loc->N("Networking"), $loc->N("Remote access")) => 'remote_access_section',
	#join('|', $loc->N("Networking"), $loc->N("WWW")) => 'networking_www_section',
	#$loc->N("Office") => 'office_section',
	#join('|', $loc->N("Office"), $loc->N("Dictionary")) => 'office_dictionary_section',
	#join('|', $loc->N("Office"), $loc->N("Finance")) => 'finances_section',
	#join('|', $loc->N("Office"), $loc->N("Management")) => 'timemanagement_section',
	#join('|', $loc->N("Office"), $loc->N("Organizer")) => 'timemanagement_section',
	#join('|', $loc->N("Office"), $loc->N("Utilities")) => 'office_accessories_section',
	#join('|', $loc->N("Office"), $loc->N("Spreadsheet")) => 'spreadsheet_section',
	#join('|', $loc->N("Office"), $loc->N("Suite")) => 'office_suite',
	#join('|', $loc->N("Office"), $loc->N("Word processor")) => 'wordprocessor_section',
	#$loc->N("Publishing") => 'publishing_section',
	#$loc->N("Sciences") => 'sciences_section',
	#join('|', $loc->N("Sciences"), $loc->N("Astronomy")) => 'astronomy_section',
	#join('|', $loc->N("Sciences"), $loc->N("Biology")) => 'biology_section',
	#join('|', $loc->N("Sciences"), $loc->N("Chemistry")) => 'chemistry_section',
	#join('|', $loc->N("Sciences"), $loc->N("Computer science")) => 'computer_science_section',
	#join('|', $loc->N("Sciences"), $loc->N("Geosciences")) => 'geosciences_section',
	#join('|', $loc->N("Sciences"), $loc->N("Mathematics")) => 'mathematics_section',
	#join('|', $loc->N("Sciences"), $loc->N("Other")) => 'other_sciences',
	#join('|', $loc->N("Sciences"), $loc->N("Physics")) => 'physics_section',
	#$loc->N("Security") => 'security_section',
	#$loc->N("Shells") => 'shells_section',
	#$loc->N("Sound") => 'sound_section',
	#join('|', $loc->N("Sound"), $loc->N("Editors and Converters")) => 'sound_editors_section',
	#join('|', $loc->N("Sound"), $loc->N("Midi")) => 'sound_midi_section',
	#join('|', $loc->N("Sound"), $loc->N("Mixers")) => 'sound_mixers_section',
	#join('|', $loc->N("Sound"), $loc->N("Players")) => 'sound_players_section',
	#join('|', $loc->N("Sound"), $loc->N("Utilities")) => 'sound_utilities_section',
	#$loc->N("System") => 'system_section',
	#join('|', $loc->N("System"), $loc->N("Base")) => 'system_section',
	#join('|', $loc->N("System"), $loc->N("Boot and Init")) => 'boot_init_section',
	#join('|', $loc->N("System"), $loc->N("Cluster")) => 'parallel_computing_section',
	#join('|', $loc->N("System"), $loc->N("Configuration")) => 'configuration_section',
	#join('|', $loc->N("System"), $loc->N("Fonts")) => 'chinese_section',
	#join('|', $loc->N("System"), $loc->N("Fonts"), $loc->N("True type")) => '',
	#join('|', $loc->N("System"), $loc->N("Fonts"), $loc->N("Type1")) => '',
	#join('|', $loc->N("System"), $loc->N("Fonts"), $loc->N("X11 bitmap")) => '',
	#join('|', $loc->N("System"), $loc->N("Internationalization")) => 'chinese_section',
	#join('|', $loc->N("System"), $loc->N("Kernel and hardware")) => 'hardware_configuration_section',
	#join('|', $loc->N("System"), $loc->N("Libraries")) => 'system_section',
	#join('|', $loc->N("System"), $loc->N("Networking")) => 'networking_configuration_section',
	#join('|', $loc->N("System"), $loc->N("Packaging")) => 'packaging_section',
	#join('|', $loc->N("System"), $loc->N("Printing")) => 'printing_section',
	#join('|', $loc->N("System"), $loc->N("Servers")) => 'servers_section',
	#join('|', $loc->N("System"),
          ##-PO: This is a package/product name. Only translate it if needed:
          #$loc->N("X11")) => 'x11_section',
	#$loc->N("Terminals") => 'terminals_section',
	#$loc->N("Text tools") => 'text_tools_section',
	#$loc->N("Toys") => 'toys_section',
	#$loc->N("Video") => 'video_section',
	#join('|', $loc->N("Video"), $loc->N("Editors and Converters")) => 'video_editors_section',
	#join('|', $loc->N("Video"), $loc->N("Players")) => 'video_players_section',
	#join('|', $loc->N("Video"), $loc->N("Television")) => 'video_television_section',
	#join('|', $loc->N("Video"), $loc->N("Utilities")) => 'video_utilities_section',

     ## for Mageia Choice:
	#$loc->N("Workstation") => 'system_section',
	#join('|', $loc->N("Workstation"), $loc->N("Configuration")) => 'configuration_section',
	#join('|', $loc->N("Workstation"), $loc->N("Console Tools")) => 'interpreters_section',
	#join('|', $loc->N("Workstation"), $loc->N("Documentation")) => 'documentation_section',
	#join('|', $loc->N("Workstation"), $loc->N("Game station")) => 'amusement_section',
	#join('|', $loc->N("Workstation"), $loc->N("Internet station")) => 'networking_section',
	#join('|', $loc->N("Workstation"), $loc->N("Multimedia station")) => 'multimedia_section',
	#join('|', $loc->N("Workstation"), $loc->N("Network Computer (client)")) => 'other_networking',
	#join('|', $loc->N("Workstation"), $loc->N("Office Workstation")) => 'office_section',
	#join('|', $loc->N("Workstation"), $loc->N("Scientific Workstation")) => 'sciences_section',
	#$loc->N("Graphical Environment") => 'graphical_desktop_section',

	#join('|', $loc->N("Graphical Environment"), $loc->N("GNOME Workstation")) => 'gnome_section',
	#join('|', $loc->N("Graphical Environment"), $loc->N("IceWm Desktop")) => 'icewm_section',
	#join('|', $loc->N("Graphical Environment"), $loc->N("KDE Workstation")) => 'kde_section',
	#join('|', $loc->N("Graphical Environment"), $loc->N("Other Graphical Desktops")) => 'more_applications_other_section',
	#$loc->N("Development") => 'development_section',
	#join('|', $loc->N("Development"), $loc->N("Development")) => 'development_section',
	#join('|', $loc->N("Development"), $loc->N("Documentation")) => 'documentation_section',
	#$loc->N("Server") => 'servers_section',
	#join('|', $loc->N("Server"), $loc->N("DNS/NIS")) => 'networking_section',
	#join('|', $loc->N("Server"), $loc->N("Database")) => 'databases_section',
	#join('|', $loc->N("Server"), $loc->N("Firewall/Router")) => 'networking_section',
	#join('|', $loc->N("Server"), $loc->N("Mail")) => 'mail_section',
	#join('|', $loc->N("Server"), $loc->N("Mail/Groupware/News")) => 'mail_section',
	#join('|', $loc->N("Server"), $loc->N("Network Computer server")) => 'networking_section',
	#join('|', $loc->N("Server"), $loc->N("Web/FTP")) => 'networking_www_section',

    #);

#sub get_icon_path {
    #my ($group, $parent) = @_;

    #my $path = $parent ? '/usr/share/icons/mini/' : '/usr/share/icons/';
    #my $icon_path = "";
    #if(defined($group_icons{$group})){
        #$icon_path = join('', $path, $group_icons{$group}, '.png');
    #}elsif(defined($group_icons{$parent."\|".$group})){
        #$icon_path = join('', $path, $group_icons{$parent."\|".$group}, '.png');
    #}else{
        #$icon_path = join('', $path, 'applications_section', '.png');
    #}
    #unless(-e $icon_path){
        #$icon_path = join('', $path, 'applications_section', '.png');
    #}
    #return $icon_path;
#}
