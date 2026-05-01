import glob

files = glob.glob('templates/sorteos/*.html')

link_str = '''                <a href="{% url 'detalle_sorteo' sorteo.id %}" class="back-link">
                    <i class="bi bi-arrow-left"></i> Volver
                </a>'''

target_str = '''                    <div class="participants-list" id="partList"></div>
                </div>'''

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        c = file.read()
        
    if link_str in c and target_str in c:
        # Avoid duplicating
        if c.index(link_str) > c.index(target_str):
            continue
            
        c = c.replace(link_str, '')
        c = c.replace(target_str, target_str + '\n' + link_str)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(c)
