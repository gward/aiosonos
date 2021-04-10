class SonosError(Exception):
    '''Raised if there is any problem communicating with the Sonos network,
    or if we receive an error from a Sonos player.
    '''
    pass


class SonosUPnPError(SonosError):
    """A UPnP Fault Code, raised in response to actions sent over the
    network.
    """
    def __init__(self, url, error_code, error_xml, error_description=""):
        """
        Args:
            message (str): The message from the server.
            error_code (str): The UPnP Error Code as a string.
            error_xml (str): The xml containing the error, as a utf-8
                encoded string.
            error_description (str): A description of the error. Default is ""
        """
        super().__init__()
        self.error_code = error_code
        self.error_description = error_description
        self.error_xml = error_xml
        self.message = "UPnP Error {} received: {} from {}".format(
            error_code, error_description, url)

    def __str__(self):
        return self.message
