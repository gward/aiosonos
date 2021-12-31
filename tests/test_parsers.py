from didl_lite import didl_lite as didl

from aiosonos import parsers


def test_parse_didl():
    # This is totally valid and didl_lite does not complain at all.
    valid_input = '''\
<?xml version="1.0"?>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
  <item id="-1" parentID="-1" restricted="true">
    <res protocolInfo="x-file-cifs:*:application/ogg:*" duration="0:07:36">x-file-cifs://tywin/music/afro_celt_sound_system-1999-volume_2_release/01.release.ogg</res>
    <r:streamContent/>
    <r:radioShowMd/>
    <upnp:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2ftywin%2fmusic%2fafro_celt_sound_system-1999-volume_2_release%2f01.release.ogg&amp;v=175</upnp:albumArtURI>
    <dc:title>Release</dc:title>
    <upnp:class>object.item.audioItem.musicTrack</upnp:class>
    <dc:creator>Afro Celt Sound System</dc:creator>
    <upnp:album>Volume 2: Release</upnp:album>
    <upnp:originalTrackNumber>1</upnp:originalTrackNumber>
    <r:albumArtist>Afro Celt Sound System</r:albumArtist>
  </item>
</DIDL-Lite>
'''

    # This one is missing 'restricted="true"', which makes didl_lite
    # complain in strict mode.
    invalid_input = '''\
<?xml version="1.0"?>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
  <item id="-1" parentID="-1">
    <res protocolInfo="x-file-cifs:*:application/ogg:*" duration="0:07:36">x-file-cifs://tywin/music/afro_celt_sound_system-1999-volume_2_release/01.release.ogg</res>
    <r:streamContent/>
    <r:radioShowMd/>
    <upnp:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2ftywin%2fmusic%2fafro_celt_sound_system-1999-volume_2_release%2f01.release.ogg&amp;v=175</upnp:albumArtURI>
    <dc:title>Release</dc:title>
    <upnp:class>object.item.audioItem.musicTrack</upnp:class>
    <dc:creator>Afro Celt Sound System</dc:creator>
    <upnp:album>Volume 2: Release</upnp:album>
    <upnp:originalTrackNumber>1</upnp:originalTrackNumber>
    <r:albumArtist>Afro Celt Sound System</r:albumArtist>
  </item>
</DIDL-Lite>
'''

    # Assert that both inputs are handled just fine.
    tests = [
        (valid_input, 'Afro Celt Sound System'),
        (invalid_input, 'Afro Celt Sound System'),
    ]
    for (input, expect_creator) in tests:
        output = parsers.parse_didl(input)
        assert len(output) == 1
        assert isinstance(output[0], didl.DidlObject)
        assert output[0].creator == expect_creator
