Commands
========

City Scrapers has several custom `Scrapy commands <https://docs.scrapy.org/en/latest/topics/commands.html#custom-project-commands>`_ 
to streamline common tasks.

genspider
---------

* Syntax: ``scrapy genspider <name> <agency> <start_url>``
* Example: ``scrapy genspider chi_planning "Chicago Plan Commission" "https://chicago.gov/"``

Scrapy's `genspider <https://docs.scrapy.org/en/latest/topics/commands.html#genspider>`_
command is subclassed for this project to handle creating the boilerplate code.

The command accepts the Spider slug, the full agency name, and a URL that should be
initially scraped. It will use this information to create a Spider, initial Pytest test
file, and fixtures for the tests. If the site uses Legistar (based on the URL), it will
use a separate template specific to Legistar sites that simplifies some commmon
functionality.

The boilerplate files won't work for all sites, and in particular they won't cover cases
where multiple pages need to be scraped, but they provide a starting point for some
setup tasks that can cause confusion.

combinefeeds
------------

* Syntax: ``scrapy combinefeeds``

Combines output files written to a storage backend into ``latest.json`` which contains
all meetings scraped, ``upcoming.json`` which only includes meetings in the future, and
a file for each agency slug (i.e. ``chi_plan_commission.json``) at the top level of the
storage backend with the most recently scraped meetings for an agency.

runall
------

* Syntax: ``scrapy runall``

This will load all spiders and run them in the same process.

validate
--------

* Syntax: ``scrapy validate <name>``
* Example: ``scrapy validate chi_plan_commission``

This command is used to run the :class:`ValidationPipeline` and ensure that a scraper is
returning valid output. This is predominantly used for CI.
