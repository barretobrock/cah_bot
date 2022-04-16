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