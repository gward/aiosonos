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
