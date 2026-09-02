import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

def get_current_time():
    """
    Returns the current time formatted as [HH:MM:SS] for logging purposes.
    
    Returns:
        str: Current time in string format [HH:MM:SS].
    """
    return datetime.now().strftime("[%H:%M:%S]")

def get_sober_colors():
    """
    Returns a predefined list of sober colors in hexadecimal format.
    These colors are used for styling edges in the generated Freeplane XML.
    
    Returns:
        list of str: A list of hexadecimal color strings.
    """
    return [
        '#FFB4A2', # Pêssego suave
        '#DDBEA9', # Areia escuro
        '#B7B7A4', # Bege esverdeado
        '#E5989B', # Salmão suave
        '#CB997E', # Terracota suave
        '#A5A58D', # Verde caqui
        '#B5838D', # Rosa desbotado
        '#9D8189', # Rosa envelhecido escuro
        '#8A817C', # Marrom acinzentado
        '#718355', # Verde oliva desbotado
        '#6B705C', # Verde musgo acinzentado
        '#6D6875', # Roxo acinzentado
        '#5C6B73', # Azul petróleo suave
        '#3D5A80', # Azul marinho sóbrio
        '#4A4E69', # Azul acinzentado escuro
        '#85182A'  # Vermelho escuro (Bordô intenso)
    ]

def _get_freeplane_hooks_xml():
    """Returns the static XML string for Freeplane styles and hooks."""
    return '''<hooks>
<hook NAME="MapStyle">
    <properties edgeColorConfiguration="#808080ff,#ff0000ff,#0000ffff,#00ff00ff,#ff00ffff,#00ffffff,#7c0000ff,#00007cff,#007c00ff,#7c007cff,#007c7cff,#7c7c00ff" auto_compact_layout="true" fit_to_viewport="false" show_icons="BESIDE_NODES" associatedTemplateLocation="template:/essay.mm" show_tags="UNDER_NODES" show_icon_for_attributes="true" show_note_icons="true" showTagCategories="false"/>
    <tags category_separator="::"/>
<map_styles>
<stylenode LOCALIZED_TEXT="styles.root_node" STYLE="oval" UNIFORM_SHAPE="true" VGAP_QUANTITY="24 pt">
<font SIZE="24"/>
<stylenode LOCALIZED_TEXT="styles.predefined" POSITION="bottom_or_right" STYLE="bubble">
<stylenode LOCALIZED_TEXT="default" ID="ID_1190209345" ICON_SIZE="12 pt" COLOR="#000000" STYLE="fork">
<arrowlink SHAPE="CUBIC_CURVE" COLOR="#000000" WIDTH="2" TRANSPARENCY="200" DASH="" FONT_SIZE="9" FONT_FAMILY="SansSerif" DESTINATION="ID_1190209345" STARTARROW="NONE" ENDARROW="DEFAULT"/>
<font NAME="SansSerif" SIZE="10" BOLD="false" ITALIC="false"/>
<richcontent TYPE="DETAILS" CONTENT-TYPE="plain/auto"/>
<richcontent TYPE="NOTE" CONTENT-TYPE="plain/auto"/>
</stylenode>
<stylenode LOCALIZED_TEXT="defaultstyle.details"/>
<stylenode LOCALIZED_TEXT="defaultstyle.tags">
<font SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="defaultstyle.attributes">
<font SIZE="9"/>
</stylenode>
<stylenode LOCALIZED_TEXT="defaultstyle.note" COLOR="#000000" BACKGROUND_COLOR="#ffffff" TEXT_ALIGN="LEFT"/>
<stylenode LOCALIZED_TEXT="defaultstyle.floating">
<edge STYLE="hide_edge"/>
<cloud COLOR="#f0f0f0" SHAPE="ROUND_RECT"/>
</stylenode>
<stylenode LOCALIZED_TEXT="defaultstyle.selection" BACKGROUND_COLOR="#afd3f7" BORDER_COLOR_LIKE_EDGE="false" BORDER_COLOR="#afd3f7"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.user-defined" POSITION="bottom_or_right" STYLE="bubble">
<stylenode LOCALIZED_TEXT="styles.ok">
<icon BUILTIN="button_ok"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.needs_action">
<icon BUILTIN="messagebox_warning"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.floating_node">
<cloud COLOR="#ffffff" SHAPE="ARC"/>
<edge STYLE="hide_edge"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.topic" COLOR="#18898b" STYLE="fork">
<font NAME="Liberation Sans" SIZE="10" BOLD="true"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.subtopic" COLOR="#cc3300" STYLE="fork">
<font NAME="Liberation Sans" SIZE="10" BOLD="true"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.subsubtopic" COLOR="#669900">
<font NAME="Liberation Sans" SIZE="10" BOLD="true"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.connection" COLOR="#606060" STYLE="fork">
<font NAME="Arial" SIZE="10" BOLD="false"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.important" ID="ID_75090151" COLOR="#ff0000">
<icon BUILTIN="yes"/>
<arrowlink COLOR="#ff3333" TRANSPARENCY="255" DESTINATION="ID_75090151"/>
<font NAME="Liberation Sans" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.question">
<icon BUILTIN="help"/>
<font NAME="Aharoni" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.key" COLOR="#996600">
<icon BUILTIN="password"/>
<font NAME="Liberation Sans" SIZE="10" BOLD="false"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.idea">
<icon BUILTIN="idea"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.note" COLOR="#990000">
<font NAME="Liberation Sans" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.date" COLOR="#0033ff">
<icon BUILTIN="calendar"/>
<font NAME="Liberation Sans" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.website" COLOR="#006633">
<font NAME="Liberation Sans" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.list" COLOR="#cc6600">
<icon BUILTIN="list"/>
<font NAME="Liberation Sans" SIZE="10" BOLD="true"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.quotation" COLOR="#338800" STYLE="fork">
<font NAME="Liberation Sans" SIZE="10" BOLD="false" ITALIC="false"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.definition" COLOR="#666600">
<font NAME="Liberation Sans" SIZE="10" BOLD="false"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.description" COLOR="#996600">
<font NAME="Liberation Sans" SIZE="10" BOLD="false"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.pending" COLOR="#b3b95c">
<font NAME="Liberation Sans" SIZE="10"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.flower" COLOR="#ffffff" BACKGROUND_COLOR="#255aba" STYLE="oval" TEXT_ALIGN="CENTER" BORDER_WIDTH_LIKE_EDGE="false" BORDER_WIDTH="22 pt" BORDER_COLOR_LIKE_EDGE="false" BORDER_COLOR="#f9d71c" BORDER_DASH_LIKE_EDGE="false" BORDER_DASH="CLOSE_DOTS" MAX_WIDTH="6 cm" MIN_WIDTH="3 cm"/>
</stylenode>
<stylenode LOCALIZED_TEXT="styles.AutomaticLayout" POSITION="bottom_or_right" STYLE="bubble">
<stylenode LOCALIZED_TEXT="AutomaticLayout.level.root" COLOR="#000000" STYLE="oval">
<font SIZE="18"/>
</stylenode>
<stylenode LOCALIZED_TEXT="AutomaticLayout.level,1" COLOR="#0033ff">
<font SIZE="16"/>
</stylenode>
<stylenode LOCALIZED_TEXT="AutomaticLayout.level,2" COLOR="#00b439">
<font SIZE="14"/>
</stylenode>
<stylenode LOCALIZED_TEXT="AutomaticLayout.level,3" COLOR="#990000">
<font SIZE="12"/>
</stylenode>
<stylenode LOCALIZED_TEXT="AutomaticLayout.level,4" COLOR="#111111">
<font SIZE="10"/>
</stylenode>
</stylenode>
</stylenode>
</map_styles>
</hook>
<hook NAME="AutomaticEdgeColor" COUNTER="4" RULE="ON_BRANCH_CREATION"/>
</hooks>'''

def _parse_line(line):
    """
    Extracts the numbering prefix and text content from a given line.
    
    Args:
        line (str): The raw text line to parse.
        
    Returns:
        tuple: A tuple containing the numbering string and the text content,
            or (None, None) if the line does not match the expected pattern.
    """
    match = re.match(r'^([\d\.]+)\s+(.*)', line)
    if not match:
        return None, None
    return match.group(1), match.group(2)

def _create_node_attributes(text_node):
    """
    Creates base XML attributes for a Freeplane node.
    
    Args:
        text_node (str): The text content to be set as the node's TEXT attribute.
        
    Returns:
        dict: A dictionary of attributes including TEXT, ID, CREATED, and MODIFIED.
    """
    current_time_ms = str(int(time.time() * 1000))
    node_id = f"ID_{current_time_ms}_{hash(text_node) % 100000}"
    return {
        'TEXT': text_node,
        'ID': node_id,
        'CREATED': current_time_ms,
        'MODIFIED': current_time_ms
    }

def _add_root_node(map_root, node_attribs, node_stack, level):
    """
    Adds the root node to the XML map and updates the node stack.
    
    Args:
        map_root (xml.etree.ElementTree.Element): The root XML element of the map.
        node_attribs (dict): Attributes for the new root node.
        node_stack (dict): Dictionary tracking the current node at each hierarchy level.
        level (int): The hierarchy level (should be 0 for root).
    """
    node_attribs['STYLE'] = 'oval'
    node_attribs['FOLDED'] = 'false'
    node_elem = ET.SubElement(map_root, 'node', node_attribs)
    
    hooks_root = ET.fromstring(_get_freeplane_hooks_xml())
    for hook in hooks_root:
        node_elem.append(hook)
        
    node_stack[level] = node_elem

def _add_child_node(node_attribs, node_stack, level, color_index, sober_colors):
    """
    Adds a child node to its appropriate parent in the hierarchy and applies styling.
    
    Args:
        node_attribs (dict): Attributes for the new node.
        node_stack (dict): Dictionary tracking the current node at each hierarchy level.
        level (int): The current node's hierarchy level (1 or higher).
        color_index (int): Index tracking the color to assign to level 1 nodes.
        sober_colors (list of str): List of available hex colors.
        
    Returns:
        int: Updated color index to be used for the next level 1 node.
    """
    if level == 1:
        node_attribs['POSITION'] = "bottom_or_right" if color_index % 2 == 0 else "top_or_left"
    
    if (level - 1) not in node_stack:
        return color_index
        
    parent_node = node_stack[level - 1]
    node_elem = ET.SubElement(parent_node, 'node', node_attribs)
    
    if level >= 1:
        color = sober_colors[(level - 1) % len(sober_colors)]
        ET.SubElement(node_elem, 'edge', {'COLOR': color})
        
    if level == 1:
        color_index += 1
        
    node_stack[level] = node_elem
    return color_index

def convert_text_to_freeplane_xml(text_content):
    """
    Converts hierarchical text content into a well-formatted Freeplane XML string.
    
    Args:
        text_content (str): The raw hierarchical text to parse and convert.
        
    Returns:
        str: A pretty-printed XML string compatible with Freeplane.
    """
    print(f"{get_current_time()} 🔹 [STEP] convert_text_to_freeplane_xml Starting text conversion")
    lines = text_content.strip().split('\n')
    map_root = ET.Element('map', {'version': 'freeplane 1.12.15'})
    map_root.append(ET.Comment('To view this file, download free mind mapping software Freeplane from https://www.freeplane.org '))
    ET.SubElement(map_root, 'bookmarks')
    
    sober_colors = get_sober_colors()
    color_index = 0
    node_stack = {}
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        numbering, text_node = _parse_line(line)
        if not numbering:
            continue
            
        level = numbering.count('.')
        node_attribs = _create_node_attributes(text_node)
        
        if level == 0:
            _add_root_node(map_root, node_attribs, node_stack, level)
        else:
            color_index = _add_child_node(node_attribs, node_stack, level, color_index, sober_colors)
            
    raw_xml = ET.tostring(map_root, 'utf-8')
    reparsed = minidom.parseString(raw_xml)
    print(f"{get_current_time()} ✅ [SUCCESS] convert_text_to_freeplane_xml Completed XML tree building")
    # Remove as linhas em branco que o minidom pode adicionar
    return '\n'.join([line for line in reparsed.toprettyxml(indent="  ").split('\n') if line.strip()])

def process_file(filename):
    """
    Reads a single .lh file, converts its content to Freeplane XML format, and saves it as a .mm file.
    
    Args:
        filename (str): The path to the .lh file to be processed.
        
    Returns:
        bool: True if the file was processed successfully, False otherwise.
    """
    print(f"{get_current_time()} 🔹 [STEP] process_file Starting with filename={filename}")
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
        xml_content = convert_text_to_freeplane_xml(content)
        
        base_name = os.path.splitext(filename)[0]
        mm_filename = f"{base_name}.mm"
        
        with open(mm_filename, 'w', encoding='utf-8') as f:
            f.write(xml_content)
            
        print(f"{get_current_time()} ✅ [SUCCESS] process_file {filename} convertido para {mm_filename}")
        return True
    except Exception as e:
        print(f"{get_current_time()} 🔴 [ERROR] process_file Failed to process {filename}: {str(e)}")
        print(f"{get_current_time()} ℹ️ [LOG] process_file Please check file encoding, permissions or format for {filename}")
        return False

def print_summary_box(total, successes, failures):
    """
    Prints a formatted visual summary box showing processing statistics.
    
    Args:
        total (int): The total number of processed items.
        successes (int): The number of successfully processed items.
        failures (int): The number of failed items.
    """
    print("╔═══════════════════════════════════════════════╗")
    print("║          Processing Summary                   ║")
    print("╠═══════════════════════════════════════════════╣")
    print(f"║ Total Processed: {total:<29}║")
    print(f"║ Successes:       {successes:<29}║")
    print(f"║ Failures:        {failures:<29}║")
    print("╚═══════════════════════════════════════════════╝")

def main():
    """
    Scans the current directory for .lh files and converts each into a Freeplane .mm file,
    logging progress, handling errors, and displaying a summary box upon completion.
    
    Returns:
        int: 0 if all processing succeeded (or no files found), 1 if any failures occurred.
    """
    print(f"{get_current_time()} 🔹 [STEP] main Starting process for current directory")
    
    cwd = os.getcwd()
    print(f"{get_current_time()} ℹ️ [LOG] main Resolving runtime context: {cwd}")
    
    lh_files = [f for f in os.listdir(cwd) if f.endswith('.lh')]
    
    if not lh_files:
        print(f"{get_current_time()} ℹ️ [LOG] main Nenhum arquivo .lh encontrado na pasta atual.")
        return 0
        
    total_files = len(lh_files)
    print(f"{get_current_time()} ℹ️ [LOG] main Encontrados {total_files} arquivos .lh para processamento.")
    
    success_count = 0
    failure_count = 0
    
    for i, filename in enumerate(lh_files, 1):
        print(f"{get_current_time()} 🔹 [STEP] main Processing item {i} of {total_files}")
        print(f"{get_current_time()} ℹ️ [LOG] main Processing: {filename} with default parameters")
        
        success = process_file(filename)
        
        if success:
            success_count += 1
            print(f"{get_current_time()} ✅ [SUCCESS] main File {filename} successfully converted")
        else:
            failure_count += 1
            print(f"{get_current_time()} 🔴 [ERROR] main File {filename} conversion failed")
            
    print_summary_box(total_files, success_count, failure_count)
    print(f"{get_current_time()} ✅ [SUCCESS] main Completed directory processing")
    
    return 1 if failure_count > 0 else 0

if __name__ == '__main__':
    exit_code = main()
    input("\nPress Enter to exit...")
    sys.exit(exit_code)