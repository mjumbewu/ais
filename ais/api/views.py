"""
Does three primary things:
* Geocoding lat/lng to addresses
* Standardizing addresses
* Providing identifiers for other systems
"""

from ais import app
from ais.models import Address, AddressProperty
from flask import Response, request
from passyunk.parser import PassyunkParser

from .errors import json_error
from .paginator import QueryPaginator
from .serializers import AddressJsonSerializer
from ..util import NotNoneDict


def json_response(*args, **kwargs):
    return Response(*args, mimetype='application/json', **kwargs)


def validate_page_param(request, paginator):
    page_str = request.args.get('page', '1')

    try:
        page_num = paginator.validate_page_num(page_str)
    except QueryPaginator.ValidationError as e:
        error = json_error(400, e.message, e.data)
        return None, error

    return page_num, None


@app.route('/addresses/<query>')
def addresses_view(query):
    """
    Looks up information about the address given in the query. Response is an
    object with the information for the matching address. The object includes:
    * A standardized, unambiguous address string
    * Address components
    * OPA #
    * DOR "ID"
    * L&I Key
    * Zoning something or other

    TODO: There are some addresses that are synonyms for each other. These need
          to be disambiguated. There is some table that has a some property that
          tells me an address is the canonical one. Which is that table? Is it
          AddressLink? Do I only want addresses that have none of a particular
          type of relationship?

          Check with Rob to about whether we should depend on the address
          summary table, and if not whether we're safe to simply join on
          stree_address, and which tables we need to be concerned with.

          Check on the unit type. Should be null, as the query will ignore them.

          Consider ignoring the unit type. There are 10-15 exceptions in the city where the same unit num exists for different unit types.

    TODO: Geocode addresses by matching against types in the following order:
          * PWD
          * DOR
          * True Range
          * Curb

    TODO: Give each address a score every time someone accesses it. This can be
          used for semi-intelligent ordering. For example, if I query for "440
          Broad St", I'll most often mean the school district building. However,
          with default ordering, a building on S Broad with a whole bunch of
          units comes up first. That's annoying. But if 440 N Broad was accessed
          a bunch of times, it should have a higher popularity score than any
          one of those units, and that should help it to the top of the list.

    TODO: Allow paginator to use skip/limit semantics instead of or in addition
          to page. Maybe allow one of page or skip but not both.

    TODO: Need a way to only return addresses that have OPA numbers. Filters?

    """
    parsed = PassyunkParser().parse(query)

    # Match a set of addresses
    filters = NotNoneDict(
        street_name=parsed['components']['street']['name'],
        address_low=parsed['components']['address']['low'] or parsed['components']['address']['full'],
        address_high=parsed['components']['address']['high'],
        street_predir=parsed['components']['street']['predir'],
        street_postdir=parsed['components']['street']['postdir'],
        street_suffix=parsed['components']['street']['suffix'],
        unit_num=parsed['components']['unit']['unit_num'],
    )
    addresses = Address.query\
        .filter_by(**filters)\
        .order_by_address()
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    normalized_address = parsed['components']['street_address']
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find addresses matching query.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    addresses_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'query': query, 'normalized': normalized_address},
        pagination=paginator.get_page_info(page_num))
    result = serializer.serialize_many(addresses_page)
    return json_response(response=result, status=200)

    # TODO: If it's not a perfect match, do we want to do something like a
    # soundex or some other fuzzy match?


@app.route('/account/<number>')
def account_number_view(number):
    """
    Looks up information about the property with the given OPA account number.
    Should only ever return one or zero corresponding addresses.

    TODO: Should this return all addresses at the property that matches the
          number? For example, number 883309000 for 1234 Market, which has
          multiple units. Is there a good way to know which one is the "real"
          one? Would the is_base logic do it?
    """
    address = Address.query\
        .join(AddressProperty, AddressProperty.street_address==Address.street_address)\
        .filter(AddressProperty.opa_account_num==number)\
        .order_by_address()\
        .first()

    # Make sure we found a property
    if address is None:
        error = json_error(404, 'Could not find property with account number.',
                           {'number': number})
        return json_response(response=error, status=404)

    # Render the response
    serializer = AddressJsonSerializer()
    result = serializer.serialize(address)
    return json_response(response=result, status=200)


@app.route('/block/<query>')
def block_view(query):
    """
    TODO: Consider matching the segment ID and finding the low and high. This
          would be instead of hardcoding a low of 0 and high of 100. Maybe this
          would go at a new route, like `segment` or `block-face`.
    """
    parsed = PassyunkParser().parse(query)
    normalized_address = parsed['components']['street_address']

    # Ensure that we can get a valid address number
    try:
        address_num = int(parsed['components']['address']['low'] or
                          parsed['components']['address']['full'])
    except ValueError:
        error = json_error(400, 'No valid block number provided.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=400)

    # Match a set of addresses
    block_num = ((address_num // 100) * 100)
    filters = NotNoneDict(
        street_name=parsed['components']['street']['name'],
        street_predir=parsed['components']['street']['predir'],
        street_postdir=parsed['components']['street']['postdir'],
        street_suffix=parsed['components']['street']['suffix'],
    )
    addresses = Address.query\
        .filter_by(**filters)\
        .filter(Address.address_low >= block_num)\
        .filter(Address.address_low < block_num + 100)\
        .order_by_address()
    paginator = QueryPaginator(addresses)

    # Ensure that we have results
    addresses_count = paginator.collection_size
    if addresses_count == 0:
        error = json_error(404, 'Could not find any address on a block matching query.',
                           {'query': query, 'normalized': normalized_address})
        return json_response(response=error, status=404)

    # Validate the pagination
    page_num, error = validate_page_param(request, paginator)
    if error:
        return json_response(response=error, status=error['status'])

    # Render the response
    block_page = paginator.get_page(page_num)
    serializer = AddressJsonSerializer(
        metadata={'query': query, 'normalized': normalized_address},
        pagination=paginator.get_page_info(page_num))
    result = serializer.serialize_many(block_page)
    return json_response(response=result, status=200)