"""
Common functions for tasks to do with parsing XML documents
"""
import os
import re
import xml.etree.cElementTree as ET


def element_to_string(element, indentation=0):
    """
    Return a string representation of an ET.Element object with indentation and
    line breaks.

    `indentation` is how many levels to indent the returned string (2 spaces
    per level).
    """
    children = ""
    for child in element:
        children += element_to_string(child, indentation=indentation + 1)
        children += os.linesep

    indentation_str = " " * (2 * indentation)
    elem_str = "{ind}<{tag}".format(ind=indentation_str, tag=element.tag)

    attrs = " ".join('{}="{}"'.format(key, value) for key, value in element.items())
    if attrs:
        elem_str += " " + attrs

    if children:
        elem_str += ">"
        elem_str += os.linesep + children
        elem_str += "{ind}</{tag}>".format(ind=indentation_str, tag=element.tag)
    else:
        elem_str += "/>"

    # If this is the top level then include <?xml?> element
    if indentation == 0:
        prolog = '<?xml version="1.0" encoding="UTF-8"?>'
        elem_str = prolog + os.linesep + elem_str
    return elem_str


def find_by_tagname(xml_filename, tagname):
    """
    Recursively search an XML document and return elements with the given tag
    name
    """
    tree = ET.ElementTree()
    tree.parse(xml_filename)
    root = tree.getroot()

    # Regex to optionally match namspace in tag name
    tag_regex = re.compile("({[^}]+})?" + tagname)
    for el in root.iter():
        if re.fullmatch(tag_regex, el.tag):
            yield el
