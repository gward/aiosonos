import asyncio


try:
    get_event_loop = asyncio.get_running_loop     # type: ignore  # Python 3.7+
except AttributeError:
    get_event_loop = asyncio.get_event_loop


def prettify(xml_text: str) -> str:
    '''Return a pretty-printed version of a unicode XML string.

    Useful for debugging.

    Args:
        xml_text (str): A text representation of XML (unicode,
            *not* utf-8).

    Returns:
        str: A pretty-printed version of the input.

    '''
    import xml.dom.minidom

    reparsed = xml.dom.minidom.parseString(xml_text)
    return reparsed.toprettyxml(indent='  ', newl='\n')


#: Commonly used namespaces, and abbreviations, used by `ns_tag`.
NAMESPACES = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
    '': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
    'ms': 'http://www.sonos.com/Services/1.1',
    'r': 'urn:schemas-rinconnetworks-com:metadata-1-0/',
}


def ns_tag(ns_id, tag):
    '''Return a namespace/tag item.

    Args:
        ns_id (str): A namespace id, eg ``"dc"`` (see `NAMESPACES`)
        tag (str): An XML tag, eg ``"author"``

    Returns:
        str: A fully qualified tag.

    The ns_id is translated to a full name space via the :const:`NAMESPACES`
    constant::

        >>> xml.ns_tag('dc','author')
        '{http://purl.org/dc/elements/1.1/}author'
    '''
    return '{{{}}}{}'.format(NAMESPACES[ns_id], tag)
