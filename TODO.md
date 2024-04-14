This file is meant to get a list of things that should be hopefully implemented or fixed
as soon as possible. 

# Near term targets

## Important
- [ ] Porting to dnf5daemon (split in more tasks)
- [ ] Porting dnfdragora-update to dnf5daemon
- [ ] Update Help and documentation
- [ ] Update and fix user settings

### Async working (old tasks to be evaluated):
- [ ] Fix transactions to make them async too (in progress, missing undo)
- [ ] Change progress bar layout (in progress)
- [ ] Add a configuration entry to avoid dnfdragora-update autostarts [87](https://github.com/manatools/dnfdragora/issues/87)
- [ ] Fix group caching if comp is selected (in progress, it works but sync now)
- [ ] Add and/or change some icons if possible (in progress thanks to Carson Black) issues ~~[55](https://github.com/manatools/dnfdragora/issues/55)~~, [139](https://github.com/manatools/dnfdragora/issues/139)
- [ ] Improve error management and user warning on errors (add transaction, etc.)

## Nice to have 
- [ ] Add a new filter "show only packages with GUI" (query.filter_file(["/usr/share/applications/*.desktop"], GLOB)) 

## Fixing
- all the [issues](https://github.com/manatools/dnfdragora/issues) of course

# Medium term targets
-   Modifying repository configuration to override settings per repository.
-   Add a way to search, enable, and disable COPR repositories
-   Handle solution errors. In the event that there's a dependency problem detected, we should
    offer the user a way to resolve it from within the UI so that it can be resolved.
-   Offer weak dependency options, handling both forward and reverse dependencies.
    With weak dependencies, we should offer a way for the user to select whether to install
    recommended/supplementary packages, add suggested/enhancing packages to the transaction, etc.
-   Handle multiple provider case. When something is provided by multiple packages, we need to be
    able to offer the user a choice and indicate a sane default based on the system package
    set and the transaction itself.

# Long term targets
-   Handle complex dependencies. If there are conditional dependencies, we should offer ways to
    select from the set of options (in the case with Requires with "or") or offer ways to enable
    additional functionality (in the case where Requires only activate if something is installed).



