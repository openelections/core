from datetime import datetime

from mongoengine import Document, DynamicDocument
from mongoengine.fields import (
    BooleanField,
    DateTimeField,
    DictField,
    IntField,
    StringField,
    ReferenceField,
)
from mongoengine.queryset import CASCADE
from mongoengine import signals

from openelex.lib.text import slugify
from openelex.us import STATE_POSTALS

# CHOICE TUPLES
PRIMARY_TYPE_CHOICES = (
    'blanket',
    'closed',
    'open',
    'semi-open',
    'semi-closed',
    'other',
)

REPORTING_LEVEL_CHOICES = (
    'state',
    'congressional_district',
    'state_legislative',
    'county',
    'precinct',
    'parish',
)

# Model mixins

class TimestampMixin(object):
    """
    A DynamicDocument with created and last-updated timestamps.

    This is a mixin rather than a base class because subclasses get
    shoved in the base classes collection in mongo.
    """
    created = DateTimeField(default=datetime.now)
    updated = DateTimeField(default=datetime.now)

    @classmethod
    def update_timestamp(cls, sender, document, **kwargs):
        """
        Set the last-updated timestamp to the current date/time.

        This is meant to be wired up as a signal handler.
        """
        # It won't work with update().
        #
        # See http://stackoverflow.com/a/12248318/386210 and
        # https://github.com/MongoEngine/mongoengine/issues/21  
        document.updated = datetime.now()


# Models

class RawResult(TimestampMixin, DynamicDocument):
    """Flat representation of raw data. Intended for use in data loaders."""
    ### META fields ###
    source = StringField(required=True, help_text="Name of data source (preferably from datasource.py). NOTE: this could be a single file among many for a given state, if results are split into different files by reporting level")
    election_id = StringField(required=True, help_text="election id, e.g. md-2012-11-06-general")
    state = StringField(required=True, choices=STATE_POSTALS)

    ### Contest fields ####
    start_date = DateTimeField(required=True)
    end_date = DateTimeField(required=True, help_text="Most often will match start date, except for multi-day primaries")
    election_type = StringField(help_text="general, primary, etc. from OpenElex metadata")
    primary_type = StringField(choices=PRIMARY_TYPE_CHOICES, help_text="blanket, closed, open, etc. from OpenElex metadata")
    #TODO: Validation that requires primary_type to be "closed"
    primary_party = StringField(help_text="Only assign for closed primaries, where voters must be registered in party to vote in the contest")
    result_type = StringField(required=True, help_text="certified/unofficial, from Openelex metadata")
    special = BooleanField(default=False, help_text="From OpenElex metadata")
    office = StringField(required=True)
    district = StringField(help_text="Only populate this if district is a distinct field in raw data already."
            "If it requires parsing, perform this as a transform step")

    ### Candidate fields ###
    #TODO: Add validation to require full_name or family_name
    full_name = StringField(max_length=300, help_text="Only if present in raw results.")
    family_name = StringField(max_length=200, help_text="Only if present in raw results.")
    given_name = StringField(max_length=200, help_text="Only if present in raw results.")
    suffix = StringField(max_length=200, help_text="Only if present in raw results.")

    ### Result fields ###
    reporting_level = StringField(required=True, choices=REPORTING_LEVEL_CHOICES)
    # See https://github.com/openelections/core/issues/46
    party = StringField(help_text="Party name as it appears in the raw data "
        "This is on result (rather than Candidate) because in some states "
        "(NY, CT, SC ...) candidates can run as the nominee for multiple parties "
        "and results will be per-party.")
    jurisdiction = StringField(required=True, help_text="Political geography from raw results, if present. E.g. county name, congressional district, precinct number."
            "Or default to state + office/district, if not present in data.")
    # See https://github.com/openelections/core/issues/46
    votes = IntField(required=True, help_text="Raw vote count for this jurisdiction")
    total_votes = IntField(help_text="Total candidate votes contest-wide, if provided in raw results.")
    vote_breakdowns = DictField(help_text="Vote totals for election day (absentee, provisional, etc.), if provided in raw results")
    winner = StringField(help_text="Winner flag, if provided in raw results.")
    write_in = StringField(help_text="Write-in flag, if provided in raw results.")

    meta = {
        'indexes': ['election_id', 'end_date', 'primary_type', 'primary_party', 'reporting_level', 'full_name', 'family_name'],
    }

    def __unicode__(self):
        bits = (
            self.election_id,
            self.contest_slug,
            self.candidate_slug,
            self.reporting_level,
            self.jurisdiction,
            self.votes,
        )
        return u'%s-%s-%s-%s-%s (%s)' % bits

    @property
    def contest_slug(self):
        """
        A slugified version of the raw contest information.

        This will not neccesarily match the slug on canonical Contest records.
        """
        slug = "%s" % self.office.lower().replace(' ', '-')
        if self.district:
            slug += "%s" % self.district.lower().replace(' ', '-')
        if self.primary_party:
            slug += "%s" % self.primary_party.replace(' ', '-')
        return slug

    @property
    def candidate_slug(self):
        """
        A slugified version of the raw candidate information.

        This will not neccesarily match the slug on canonical Candidate records.
        """
        if self.full_name:
            name = self.full_name
        else:
            name = self.family_name
            if self.given_name:
                name += " %s" % self.given_name
            if self.additional_name:
                name += " %s" % self.additional_name
            if self.suffix:
                name +=  " %s" % self.suffix
        return name.replace(' ', '-')
    
signals.pre_save.connect(TimestampMixin.update_timestamp, sender=RawResult)


class Office(Document):
    # We use 'US' as a fake state for offices like president
    OFFICE_STATES = STATE_POSTALS + ['US',]

    state = StringField(choices=OFFICE_STATES, required=True)
    name = StringField(required=True)
    district = StringField()
    chamber = StringField()

    def __unicode__(self):
        return u'%s' % self.key

    @classmethod
    def make_key(cls, state, name, district=None):
        key = "%s %s" % (state, name)
        if district:
            key += " (%s)" % district
        return key

    @property
    def key(self):
        return self.make_key(self.state, self.name, self.district)

    @property
    def slug(self):
        """
        Returns slugified office in format "name-district".

        Example: 

        >>> office = Office(state="MD", name="House of Delegates", district="35B", chamber="lower")
        >>> office.slug
        u'house-of-delegates-35b'
        """
        slug = slugify(self.name, '-')
        if self.district:
            slug += "-%s" % slugify(self.district, '-') 
        return slug


class Party(Document):
    name = StringField(required=True)
    abbrev = StringField(required=True)
    description = StringField()

    def __unicode__(self):
        return u'%s (%s)' % (self.name, self.abbrev)

    @classmethod
    def make_key(cls, abbrev):
        return abbrev

    @property
    def key(self):
        return self.make_key(self.abbrev)

    @property
    def slug(self):
        return slugify(self.abbrev)


class Person(TimestampMixin, DynamicDocument):
    """Unique person records

    identifiers = {
        'bioguide' : <bioguide_id>,
        'fec' : [<fecid_1>, <fecid_2>, ...],
        'votesmart' : <votesmart_id>,
        ...
    }

    """
    ### Person fields ###
    given_name = StringField(max_length=200, required=True)
    family_name = StringField(max_length=200, required=True)
    suffix = StringField(max_length=200)
    additional_name = StringField(max_length=200, help_text="For middle names, nicknames, etc")
    slug = StringField(max_length=300, required=True, help_text="Slugified name for easier querying and obj repr")
    identifiers = DictField(help_text="Unique identifiers for candidate in other data sets, such as FEC Cand number."
            "This stores full history of all unique IDs, such as all FEC Cand numbers over time.")

    def __unicode__(self):
        return "%s" % self.full_name

    @property
    def full_name(self):
        bits = (self.given_name,)
        if self.additional_name:
            bits += (self.additional_name,)
        bits += (self.family_name,)
        if self.suffix:
            bits += (self.suffix)
        name = " ".join(bits)
        return name

signals.pre_save.connect(TimestampMixin.update_timestamp, sender=Person)


class Contest(TimestampMixin, DynamicDocument):
    ### Meta fields ###
    source = StringField(required=True, help_text="Name of data source (preferably from datasource.py). NOTE: this could be a single file among many for a given state, if results are split into different files by reporting level")
    election_id = StringField(required=True, help_text="election id, e.g. md-2012-11-06-general")
    state = StringField(required=True, choices=STATE_POSTALS)

    ### Contest fields ###
    start_date = DateTimeField(required=True)
    end_date = DateTimeField(required=True, help_text="Most often will match start date, except for multi-day primaries")
    election_type = StringField(help_text="general, primary, etc. from OpenElex metadata")
    primary_type = StringField(choices=PRIMARY_TYPE_CHOICES, help_text="blanket, closed, open, etc. from OpenElex metadata")
    #TODO: Validation that requires primary_type to be "closed"
    result_type = StringField(required=True, help_text="certified/unofficial, from Openelex metadata")
    special = BooleanField(default=False, help_text="From OpenElex metadata")
    office = ReferenceField(Office, required=True, help_text="Standardized office")
    primary_party = ReferenceField(Party, help_text="This should only be assigned for closed primaries, where voters must be registered in party to vote in the contest")
    slug = StringField(required=True, help_text="Slugified office name, plus district and party if relevant")

    meta = {
        'indexes': ['election_id',],
    }

    def __unicode__(self):
        return u'%s-%s' % self.key

    @property
    def key(self):
        return (self.election_id, self.slug)

    def _make_slug(self):
        """
        Returns a slug suitable for setting self.slug
        """
        # TODO: Confirm that it's ok that we'll possible have dupes here
        # across elections since this is only based on office and primary
        # party. This is the way it's done traditionally at least
        slug = self.office.slug
        if self.primary_party:
            slug += "-%s" % self.primary_party.slug 
        return slug

    @classmethod
    def post_init(cls, sender, document, **kwargs):
        if not document.slug:
            document.slug = document._make_slug()

signals.post_init.connect(Contest.post_init, sender=Contest)
signals.pre_save.connect(TimestampMixin.update_timestamp, sender=Contest)


class Candidate(TimestampMixin, DynamicDocument):
    """
    State is included because in nearly all cases, a candidate 
    is unique to a state (presidential races involve state-level 
    candidacies). This helps with lookups and prevents duplicates.

    """
    ### Meta fields ###
    source = StringField(required=True, help_text="Name of data source (preferably from datasource.py). NOTE: this could be a single file among many for a given state, if results are split into different files by reporting level")
    election_id = StringField(required=True, help_text="election id, e.g. md-2012-11-06-general")
    state = StringField(required=True, choices=STATE_POSTALS)

    person = ReferenceField(Person, help_text="Reference to unique Person record to link candidacies over time and/or across states for presidential cands.")

    ### Contest fields ####
    contest = ReferenceField(Contest, reverse_delete_rule=CASCADE, required=True)
    contest_slug = StringField(required=True, help_text="Denormalized contest slug for easier querying and obj repr")

    ### Candidate fields ###
    #TODO: Add validation to require full_name or famly_name, assuming we allow full_name (see question above)
    full_name = StringField(max_length=200)
    family_name = StringField(max_length=75)
    given_name = StringField(max_length=50)
    suffix = StringField(max_length=20)
    additional_name = StringField(max_length=75, help_text="Middle name, nickname, etc., if provided in raw results.")
    #TODO: Add validation to require full_name or family_name
    #TODO: Add example to help_text for slugified name
    slug = StringField(max_length=300, required=True, help_text="Slugified name for easier querying and obj repr")
    identifiers = DictField(help_text="Unique identifiers for candidate in other data sets, such as FEC Cand number. "
            "This should store IDs relevant to just this candidacy, such as FEC Cand number(s) for a particular election "
            "cycle. The Person model will store the full history of all FEC Cand Numbers")

    meta = {
        'indexes': ['election_id',],
    }

    def __unicode__(self):
        name =  u'%s - %s' % (self.contest_slug, self.name)
        return name

    @property
    def name(self):
        if self.full_name:
            name = self.full_name
        else:
            name = self.family_name
            if self.given_name:
                name += " %s" % self.given_name
            if self.additional_name:
                name += " %s" % self.additional_name
            if self.suffix:
                name +=  " %s" % self.suffix
            name = "%s" % self.family_name
        return name

    @property
    def key(self):
        return (self.election_id, self.contest_slug, self.slug)

    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        if not document.contest_slug:
            document.contest_slug = document.contest.slug

        if not document.slug:
            document.slug = slugify(document.full_name, '-')

signals.pre_save.connect(TimestampMixin.update_timestamp, sender=Candidate)
signals.pre_save.connect(Candidate.pre_save, sender=Candidate)


class Result(TimestampMixin, DynamicDocument):
    ### Meta fields ###
    source = StringField(required=True, help_text="Name of data source for this file, preferably standardized filename from datasource.py")
    election_id = StringField(required=True, help_text="election id, e.g. md-2012-11-06-general")
    state = StringField(required=True, choices=STATE_POSTALS)

    ### Contest ###
    contest = ReferenceField(Contest, reverse_delete_rule=CASCADE, required=True)
    contest_slug = StringField(required=True, help_text="Denormalized contest slug for easier querying and obj repr")

    ### Candidate ###
    candidate = ReferenceField(Candidate, reverse_delete_rule=CASCADE, required=True)
    candidate_slug = StringField(required=True, help_text="Denormalized candidate slug for easier querying and obj repr")

    ### Result fields ###
    reporting_level = StringField(required=True, choices=REPORTING_LEVEL_CHOICES)
    #TODO: Add validation: If aggregated_from_level is filled in raw_result must be blank.
    raw_result = ReferenceField(RawResult, help_text="Reference this raw result only if it is NOT aggregate of lower-level results")
    aggregated_from_level = StringField(choices=REPORTING_LEVEL_CHOICES, help_text="If this is aggregate result, such as "
        "racewide from county, designate the reporting_level it was aggregated up from.")
    # See https://github.com/openelections/core/issues/46
    party = StringField(help_text="Standaridzed party ID/abbrev. "
        "This is on result (rather than Candidate) because in some states "
        "(NY, CT, SC ...) candidates can run as the nominee for multiple parties "
        "and results will be per-party.")
    ocd_id = StringField(help_text="OCD ID of jurisdiction, e.g. state, county, state leg. precinct, etc")
    jurisdiction = StringField(required=True, help_text="Derived/standardized political geography (state, county, district, etc.).")
    votes = IntField(required=True, help_text="Vote count for this jurisdiction")
    total_votes = IntField(help_text="Total candidate votes contest-wide, either from raw results or calculated by OpenElex."
            "Requires validation if migrated from raw results.")
    vote_breakdowns = DictField(help_text="If provided, store vote totals for election day, absentee, provisional, etc.")
    winner = BooleanField(help_text="Winner of jurisdiction, *not* contest winner. Some data flags lower-level results "
        "as winner if candidate won contest-wide. In such case, this field should blank")
    write_in = BooleanField()

    meta = {
        'indexes': ['election_id',],
    }

    def __unicode__(self):
        bits = (
            self.election_id,
            self.contest_slug,
            self.candidate_slug,
            self.reporting_level,
            self.jurisdiction,
            self.votes,
        )
        return u'%s-%s-%s-%s-%s (%s)' % bits

    @classmethod
    def pre_save(cls, sender, document, **kwargs):
        if not document.contest_slug:
            document.contest_slug = document.contest.slug

        if not document.candidate_slug:
            document.candidate_slug = document.candidate.slug

signals.pre_save.connect(TimestampMixin.update_timestamp, sender=Result)
signals.pre_save.connect(Result.pre_save, sender=Result)
