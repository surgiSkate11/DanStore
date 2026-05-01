import glob, re

files = glob.glob('templates/sorteos/*.html')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        c = file.read()
        
    m_back = re.search(r'\n[ \t]*<a href="\{% url \'detalle_sorteo\' sorteo\.id %\}\" class=\"back-link\">.*?</a>', c, re.DOTALL)
    if m_back:
        back_link_str = m_back.group(0)
        # Remove from current location
        c = c.replace(back_link_str, '')
        
        # Insert back link right after <div class="participants-list" id="partList"></div>
        # or just before </div>\n            </div>\n        </div>\n    </div>
        # Looking at structure:
        #                    <div class="participants-list" id="partList"></div>
        #                </div>
        
        insert_marker = '<div class="participants-list" id="partList"></div>\n                </div>'
        if insert_marker in c:
            c = c.replace(insert_marker, insert_marker + back_link_str)
        else:
            print("Could not find insert marker in " + f)
            
        with open(f, 'w', encoding='utf-8') as file:
            file.write(c)
