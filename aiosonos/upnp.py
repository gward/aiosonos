from __future__ import annotations

import logging
from xml.sax import saxutils
from xml.etree import ElementTree
from typing import Optional, Any, Dict, List, Tuple

import aiohttp.client

from . import utils, errors

log = logging.getLogger(__name__)

# type aliases
SOAPArgs = Optional[List[Tuple[str, Any]]]


class UPnPService:
    service_type: str
    version: int
    control_url: str
    scpd_url: str
    event_subscription_url: str

    def __init__(self):
        self.service_type = self.__class__.__name__
        self.version = 1

        # The UPnP Control URL.
        self.control_url = "{}/Control".format(self.service_type)
        # The service control protocol description URL.
        self.scpd_url = "xml/{}{}.xml".format(self.service_type, self.version)
        # The service event subscription URL.
        self.event_subscription_url = "{}/Event".format(self.service_type)

        # From table 3.3 in
        # http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
        # This list may not be complete, but should be good enough to be going
        # on with.  Error codes between 700-799 are defined for particular
        # services, and may be overriden in subclasses. Error codes >800
        # are generally SONOS specific. NB It may well be that SONOS does not
        # use some of these error codes.

        # pylint: disable=invalid-name
        self.upnp_errors = {
            400: "Bad Request",
            401: "Invalid Action",
            402: "Invalid Args",
            404: "Invalid Var",
            412: "Precondition Failed",
            501: "Action Failed",
            600: "Argument Value Invalid",
            601: "Argument Value Out of Range",
            602: "Optional Action Not Implemented",
            603: "Out Of Memory",
            604: "Human Intervention Required",
            605: "String Argument Too Long",
            606: "Action Not Authorized",
            607: "Signature Failure",
            608: "Signature Missing",
            609: "Not Encrypted",
            610: "Invalid Sequence",
            611: "Invalid Control URL",
            612: "No Such Session",
        }


class ZoneGroupTopology(UPnPService):
    """Sonos zone group topology service, for functions relating to network
    topology, diagnostics and updates."""
    pass


SERVICE_TOPOLOGY = ZoneGroupTopology()


class UPnPClient:
    '''An object for sending UPnP requests to a single player.'''

    SOAP_BODY_TEMPLATE = (
        '<?xml version="1.0"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body>'
        '<u:{action} xmlns:u="urn:schemas-upnp-org:service:'
        '{service_type}:{version}">'
        '{arguments}'
        '</u:{action}>'
        '</s:Body>'
        '</s:Envelope>'
    )  # noqa PEP8

    def __init__(
            self,
            base_url: str,
            session: aiohttp.client.ClientSession):
        self.base_url = base_url
        self.session = session

    async def send_command(
            self,
            service: UPnPService,
            action: str,
            args: SOAPArgs = None) -> Dict[str, Any]:
        '''Send a command to a Sonos device.

        Args:
            action (str): the name of an action (a string as specified in the
                service description XML file) to be sent.
            args (list, optional): Relevant arguments as a list of (name,
                value) tuples

        Returns:
             dict: a dict of ``{argument_name, value}`` items.

        Raises:
            `AttributeError`: If this service does not support the action.
            `ValueError`: If the argument lists do not match the action
                signature.
            `SoCoUPnPException`: if a SOAP error occurs.
            `UnknownSoCoException`: if an unknonwn UPnP error occurs.

        '''
        assert args is None, 'args not supported yet'

        headers, body = self.build_command(service, action, args)
        url = self.base_url + service.control_url
        log.info('Sending %s %s to %s', action, args, url)
        log.debug('Sending %s, %s', headers, utils.prettify(body))
        # Convert the body to bytes, and send it.
        response = await self.session.post(
            url, headers=headers, data=body.encode())
        async with response:
            response_text = await response.text()

        #log.debug('Received %s, %s', response.headers, response_text)
        status = response.status
        log.info('Received status %s', status)
        if status == 200:
            # The response is good. Get the output params, and return them.
            # NB an empty dict is a valid result. It just means that no
            # params are returned. By using response_text, we rely upon
            # aiohttp to convert to unicode for us.
            result = self.unwrap_arguments(response_text)
            return result
        elif status == 500:
            # Internal server error. UPnP requires this to be returned if the
            # device does not like the action for some reason. The returned
            # content will be a SOAP Fault. Parse it and raise an error.
            self.raise_upnp_error(service, url, response_text)
        else:
            # Something else has gone wrong -- let aiohttp handle it.
            response.raise_for_status()
        raise AssertionError('unreachable')

    def build_command(
            self,
            service: UPnPService,
            action: str,
            args: SOAPArgs = None) -> Tuple[Dict, str]:
        '''Build a SOAP request.

        Args:
            action (str): the name of an action (a string as specified in the
                service description XML file) to be sent.
            args (list, optional): Relevant arguments as a list of (name,
                value) tuples.

        Returns:
            tuple: a tuple containing the POST headers (as a dict) and a
                string containing the relevant SOAP body. Does not set
                content-length, or host headers, which are completed upon
                sending.
        '''

        # A complete request should look something like this:

        # POST path of control URL HTTP/1.1
        # HOST: host of control URL:port of control URL
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # SOAPACTION: "urn:schemas-upnp-org:service:serviceType:v#actionName"
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionName
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>in arg value</argumentName>
        #           ... other in args and their values go here, if any
        #       </u:actionName>
        #   </s:Body>
        # </s:Envelope>

        arguments = self.wrap_arguments(args)
        body = self.SOAP_BODY_TEMPLATE.format(
            arguments=arguments,
            action=action,
            service_type=service.service_type,
            version=service.version,
        )
        soap_action_template = (
            'urn:schemas-upnp-org:service:{service_type}:{version}#{action}'
        )
        soap_action = soap_action_template.format(
            service_type=service.service_type, version=service.version, action=action
        )
        headers = {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPACTION': soap_action,
        }
        # Note that although we set the charset to utf-8 here, in fact the
        # body is still a str. It will only be converted to bytes when it
        # is set over the network
        return (headers, body)

    def raise_upnp_error(self, service: UPnPService, url: str, xml_error: str):
        """Dissect a UPnP error, and raise an appropriate exception.

        Args:
            xml_error (str):  a unicode string containing the body of the
                UPnP/SOAP Fault response. Raises an exception containing the
                error code.
        """

        # An error code looks something like this:

        # HTTP/1.1 500 Internal Server Error
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8"
        # DATE: when response was generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version

        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <s:Fault>
        #           <faultcode>s:Client</faultcode>
        #           <faultstring>UPnPError</faultstring>
        #           <detail>
        #               <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
        #                   <errorCode>error code</errorCode>
        #                   <errorDescription>error string</errorDescription>
        #               </UPnPError>
        #           </detail>
        #       </s:Fault>
        #   </s:Body>
        # </s:Envelope>
        #
        # All that matters for our purposes is the errorCode.
        # errorDescription is not required, and Sonos does not seem to use it.

        # NB need to encode unicode strings before passing to ElementTree
        error = ElementTree.fromstring(xml_error)
        log.debug("Error %s", xml_error)
        error_code = error.findtext(".//{urn:schemas-upnp-org:control-1-0}errorCode")
        if error_code is not None:
            description = service.upnp_errors.get(int(error_code), "")
            raise errors.SonosUPnPError(
                url=url,
                error_code=error_code,
                error_description=description,
                error_xml=xml_error,
            )

        # Unknown error, so just return the entire response
        log.error("Unknown error received from %s", url)
        raise errors.SonosError(xml_error)

    @staticmethod
    def wrap_arguments(args=None):
        """Wrap a list of tuples in xml ready to pass into a SOAP request.

        Args:
            args (list):  a list of (name, value) tuples specifying the
                name of each argument and its value, eg
                ``[('InstanceID', 0), ('Speed', 1)]``. The value
                can be a string or something with a string representation. The
                arguments are escaped and wrapped in <name> and <value> tags.

        Example:

            >>> from soco import SoCo
            >>> device = SoCo('192.168.1.101')
            >>> s = Service(device)
            >>> print(s.wrap_arguments([('InstanceID', 0), ('Speed', 1)]))
            <InstanceID>0</InstanceID><Speed>1</Speed>'
        """
        if args is None:
            args = []

        tags = []
        for name, value in args:
            tag = "<{name}>{value}</{name}>".format(
                name=name,
                value=saxutils.escape(str(value), {'"': "&quot;"})
            )
            tags.append(tag)

        xml = "".join(tags)
        return xml

    @staticmethod
    def unwrap_arguments(xml_response: str) -> Dict[str, str]:
        """Extract arguments and their values from a SOAP response.

        Args:
            xml_response (str):  SOAP/xml response text (unicode,
                not utf-8).
        Returns:
             dict: a dict of ``{argument_name: value}`` items.
        """

        # A UPnP SOAP response (including headers) looks like this:

        # HTTP/1.1 200 OK
        # CONTENT-LENGTH: bytes in body
        # CONTENT-TYPE: text/xml; charset="utf-8" DATE: when response was
        # generated
        # EXT:
        # SERVER: OS/version UPnP/1.0 product/version
        #
        # <?xml version="1.0"?>
        # <s:Envelope
        #   xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #   s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #       <u:actionNameResponse
        #           xmlns:u="urn:schemas-upnp-org:service:serviceType:v">
        #           <argumentName>out arg value</argumentName>
        #               ... other out args and their values go here, if any
        #       </u:actionNameResponse>
        #   </s:Body>
        # </s:Envelope>

        # Get all tags in order.
        tree = ElementTree.fromstring(xml_response)
        # try:
        #     tree = ElementTree.fromstring(xml_response)
        # except XML.ParseError:
        #     # Try to filter illegal xml chars (as unicode), in case that is
        #     # the reason for the parse error
        #     filtered = illegal_xml_re.sub("", xml_response.decode("utf-8")).encode(
        #         "utf-8"
        #     )
        #     tree = ElementTree.fromstring(filtered)

        # Get the first child of the <Body> tag which will be
        # <{actionNameResponse}> (depends on what actionName is). Turn the
        # children of this into a {tagname, content} dict. XML unescaping
        # is carried out for us by elementree.
        element = tree.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")
        assert element is not None
        action_response = element[0]
        return dict((i.tag, i.text or "") for i in action_response)


_session = None


def get_upnp_client(ip_address: str) -> UPnPClient:
    global _session
    if _session is None:
        _session = aiohttp.ClientSession()

    base_url = 'http://{}:1400/'.format(ip_address)
    return UPnPClient(base_url, _session)
