# Changelog

All notable changes to this project will be documented in this file. 

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

_Note: 'Unreleased' section below is used for untagged changes that will be issued with the next version bump_

### [Unreleased] - 2022-00-00 
#### Added
#### Changed
#### Deprecated
#### Removed
#### Fixed
#### Security
__BEGIN-CHANGELOG__
 
### [2.1.4] - 2022-06-04
#### Fixed
 - [GH-9](../../issues/9) - Inconsistencies when restarting cah instance with a live game
 - Ensure other player round attributes are restored (nuked hands, picks)
 
### [2.1.3] - 2022-06-03
#### Added
 - [GH-6](../../issues/6) - Improve main menu structure
#### Fixed
 - [GH-2](../../issues/2) - Player picks showing up before prompt
 - [GH-8](../../issues/8) - Toggling judge ping not picked up in game
 
### [2.1.2] - 2022-06-01
#### Fixed
 - Streak determination was causing a failure when `end-game` was called for a game that had no completed rounds
 - New game form, due to that error above, was not rendering new game button, as the game object wasn't entirely removed. It will now show if the game object still exists, but is in the `ENDED` status.
 
### [2.1.1] - 2022-05-31
#### Fixed
 - Form addresses that ended up not being used, but were causing mass selections and errors when players made selections from the form

### [2.1.0] - 2022-05-20
#### Added
 - Tables to store all game info outside of runtime
 - Setting to look for previous, unended game on bootup
 - Pick/Choice handling objects 
 - Task scheduling capability
 - Cron endpoints
#### Changed
 - Players on ARP/ARC are now hidden for privacy
 - Game / Player queries were broken out into their own files - this is mainly to better organize testing
#### Removed
 - Answer / Question card objects - these were redundant considering the related table objects
 
### [2.0.11] - 2022-05-20
#### Added
 - Improved testing on display_points
 - Recent streak determination in display_points
#### Changed
 - Made output of `display_points` better for mobile (narrower)
 - Turned off message replacement in favor of message deletion.
#### Fixed
 - Player ranks now work properly, players are now sorted by rank
 
### [2.0.10] - 2022-05-16
#### Added
 - display_points tests
#### Fixed
 - Refactored display_points to fix naming conflict
 
### [2.0.9] - 2022-05-15
#### Fixed
 - Resolve attribute error on empty event dict
 
### [2.0.8] - 2022-05-15
#### Added
 - Table transfer script
 - Rank changes
#### Changed
 - Officially run on Python 3.10 now
 - Logging in tests now correctly relies on the `pukr` library
 - Rank determination switch from 'dense' to 'first'. i.e., multiple players can no longer take the same place if they have the same score.
#### Fixed
 - Displayed scores now map back to the right player
 
### [2.0.7] - 2022-04-15
#### Added
 - `is_picked` player attribut to match what's in the table, along with getter/setter methods
#### Changed
 - Player pick enforcement
#### Fixed
 - Player display names now update in-game upon refresh
 
### [2.0.6] - 2022-04-15
#### Added
 - Methods to replace the mapped subqueries that were causing problems
#### Changed
 - Removed reliance (for now) on subqueries as saved means of extracting stats. This causes hard-to-anticipate errors.
 - Table round getters didn't need to join
#### Fixed
 - Method for refreshing players had unfortunately the same name as a child method
 - Edge case when judge leaves game taken into account
 - Fixed bad assumption that `bool` would be automagically cast as `int` when writing to an `Integer` column
 
### [2.0.5] - 2022-04-15
#### Fixed
 - table object refresher wasn't returning anything
 
### [2.0.4] - 2022-04-15
#### Fixed
 - Error logging works again
 
### [2.0.3] - 2022-04-15
#### Added
 - command search capability
#### Changed
 - improve command structure to account for tagging
 
### [2.0.2] - 2022-04-08
#### Added
 - test files for all the package modules
 - some initial test cases
#### Changed
 - logging now uses `loguru`
 
### [2.0.1] - 2022-04-08
#### Added
 - CHANGELOG
 - pyproject.toml
 - poetry.lock
#### Changed
 - Completed switch to poetry
 - Shifted to new PPM routine for package management
#### Deprecated
 - Versioneer
#### Removed
 - Lots of PPM-dependent files
 


__END-CHANGELOG__