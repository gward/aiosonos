from aiosonos import utils


def test_prettify():
    input = '<?xml version="1.0" encoding="utf-8"?><foo><bar x="y">hello</bar></foo>'
    expect = '''\
<?xml version="1.0" ?>
<foo>
  <bar x="y">hello</bar>
</foo>
'''
    assert utils.prettify(input) == expect

    input = 'this is not XML'
    assert utils.prettify(input) == input
