Constants
=========

This package defines several constants to standardize the values of meeting
classifications and status.

==============
Classification
==============

Meeting classifications are used to describe the type of meeting taking place. The `Open
Civic Data Event specification <https://opencivicdata.readthedocs.io/en/latest/data/event.html>`_
requires this field but doesn't specify allowed values. These categories are based off
of the meetings we've encountered and are an attempt to simplify the information we're
scraping.

For many agencies all of their meetings will have the same classification, but the most
common example of needing to use multiple classifications would be boards that hold
separate committee meetings. In that case, meetings of the overall board would have the
``BOARD`` classification while each committee would be classified with ``COMMITTEE``.

``ADVISORY_COMMITTEE``
----------------------

Advisory bodies that typically don't directly oversee the administration of any
governmental functions. Examples would be citizen's advisory councils or technical
advisory committees. These will typically

``BOARD``
---------

Any board of directors or body that oversees an agency or governmental function. In most
cases "Board" will be in the name.

``CITY_COUNCIL``
----------------

Any local government legislative body, also including county-level agencies like the
Cook County Board of Commissioners. This is mainly distinguished from the others in that
meetings with this classification will consist of elected rather than appointed members.

``COMMISSION``
--------------

Similar to boards, but typically commissions are set up for more focused purposes.
Should generally be used if "Commission" is in an agency name.

``COMMITTEE``
-------------

Represents a committee of a ``BOARD`` or ``COMMISSION``. This will rarely be used as an
agency's default classification, and in most cases will only be set when the meeting
title indicates that a committee will be meeting instead of the full body.

``FORUM``
---------

Any town hall, feedback session, or other type of meeting where a wide audience of the
public is invited outside of a general public comment period. These meetings usually
don't include binding votes.

``POLICE_BEAT``
---------------

Meetings of police beats, only used for police departments.

``NOT_CLASSIFIED``
------------------

Default value for meetings that don't fit in the other categories. This should almost
never be used, including as a default since most agencies will have a default
classification that fits better if one can't clearly be determined for a meeting.

======
Status
======

All allowed status values come from the allowed values in the `Open Civic Data Event
specification <https://opencivicdata.readthedocs.io/en/latest/data/event.html>`_. In
general, these are set in pipelines to handle logic around cancellation, and
``CANCELLED`` is the only one you might need to interact with directly outside of
testing.

``CANCELLED``
-------------

Indicates that a particular instance of a meeting has been cancelled. This applies to
the initially planned time of a meeting that was rescheduled, because the meeting is no
longer occurring at a specific time and the new time will be treated as a separate
meeting.

``TENTATIVE``
-------------

An internal status indicating that a meeting is far enough into the future that the
details may change.

``CONFIRMED``
-------------

Indicates that a meeting's details have been confirmed. In our case this is
automatically set when the meeting is in the near future.

``PASSED``
----------

Meetings that have already happened. Will mostly be set automatically.
