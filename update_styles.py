import glob, re

files = glob.glob('templates/sorteos/*.html')
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        c = file.read()
        
    c = re.sub(r'padding:\s*10px\s*12px;', 'padding: 8px 10px;', c)
    c = re.sub(r'gap:\s*8px;\s*border:\s*1px\s*solid\s*rgba\(255,\s*255,\s*255,\s*0\.8\);', 'gap: 6px; border: 1px solid rgba(255, 255, 255, 0.8);', c)
    c = re.sub(r'font-size:\s*0\.8rem;\s*font-weight:\s*700;\s*color:\s*#374151;\s*margin:\s*0;', 'font-size: 0.75rem; font-weight: 700; color: #374151; margin: 0;', c)
    c = re.sub(r'width:\s*70px;\s*text-align:\s*center;\s*border:\s*2px\s*solid\s*#e5e7eb;\s*border-radius:\s*8px;\s*padding:\s*2px\s*4px;', 'width: 55px; text-align: center; border: 2px solid #e5e7eb; border-radius: 8px; padding: 1px 4px; font-size: 0.85rem;', c)
    
    # Text align proximo premio
    c = re.sub(r'(\.premio-box\s*\{\s*[^}]*)border-left:\s*5px\s*solid\s*#3b82f6;([^}]*\})', r'\1text-align: center; border-left: none;\2', c)
    c = re.sub(r'(\.premio-box\s*\.name\s*\{\s*[^}]*display:\s*flex;)', r'\1 justify-content: center;', c)
    c = re.sub(r'\.premio-box\s*\.name\s*i\s*\{\s*color:\s*#3b82f6;\s*font-size:\s*1\.25rem;\s*\}', '.premio-box .name i { color: #3b82f6; font-size: 1.45rem; margin-right: 2px; }', c)
    
    # Increase participant icon size inside script
    c = re.sub(r'(class=[\'\"]bi bi-person-fill[\'\"][^>]*font-size:\s*)0\.95rem;', r'\g<1>1.25rem;', c)
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(c)
