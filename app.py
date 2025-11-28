import streamlit as st
import pandas as pd
import re

# --- DE LOGICA FUNCTIE ---
def determine_path(df, metadata):
    path = ["Start"]
    
    # 1. DATA EXTRACTIE (Op basis van je CSV snippet)
    # We zoeken de kolommen op basis van namen, aannemende dat de dataframe schoon is
    # In werkelijkheid moet je hier flexibel zijn met kolomnamen
    
    # Check LAN Reductie (> 50% voor > 1 parameter)
    # We kijken of er in de kolom 'LAN_reductie' waarden > 50 staan
    # We tellen hoeveel stoffen dit hebben
    lan_reducties = pd.to_numeric(df['reductie_lan'], errors='coerce').fillna(0)
    n_high_reductie = (lan_reducties > 50).sum()
    
    # Haal pH op
    ph_val = metadata.get('ph_kcl', 7.0)
    
    # Check type vervuiling (Regex op de namen van de stoffen)
    stoffen = df['stofnaam'].astype(str)
    
    has_oil_heavy = any(stoffen.str.contains(r'C20|C30|C40', case=False, regex=True) & (lan_reducties > 0))
    has_oil_light = any(stoffen.str.contains(r'C10-C20|C10-C12', case=False, regex=True) & (lan_reducties > 0))
    
    # Metalen regex (Pb, Hg, Cr zijn zwaar/moeilijk)
    has_metals_hard = any(stoffen.str.contains(r'Lood|Pb|Kwik|Hg|Chroom|Cr', case=False, regex=True) & (lan_reducties > 0))
    # Metalen regex (Zn, Cd, Ni, Co zijn lichter)
    has_metals_easy = any(stoffen.str.contains(r'Zink|Zn|Cadmium|Cd|Nikkel|Ni|Kobalt|Co|Koper|Cu', case=False, regex=True) & (lan_reducties > 0))

    # Bepaal Type
    is_mix = (has_oil_heavy or has_oil_light) and (has_metals_hard or has_metals_easy)
    is_org = (has_oil_heavy or has_oil_light) and not is_mix
    is_met = (has_metals_hard or has_metals_easy) and not is_mix

    # --- STAP 1: LAN CHECK ---
    path.append("CheckLAN")
    if n_high_reductie <= 1:
        path.append("PilotReg")
        return path # Einde
    
    # --- STAP 2: TYPE CHECK ---
    path.append("CheckType")
    current_type = ""
    
    if is_mix:
        path.append("Mix")
        current_type = "Mix"
    elif is_met:
        path.append("Met")
        current_type = "Met"
    else:
        path.append("Org")
        current_type = "Org"
        
    # --- STAP 3: COMPLEXITEIT ---
    is_hard_route = False
    
    # Direct naar Moeilijk?
    if current_type == "Mix" and (has_metals_hard or has_oil_heavy): is_hard_route = True
    if current_type == "Met" and has_metals_hard: is_hard_route = True
    if current_type == "Org" and has_oil_heavy: is_hard_route = True
    
    if is_hard_route:
        path.append("RouteHard")
    else:
        # Potentieel makkelijk - Checks uitvoeren
        if current_type == "Org":
            path.append("TestMob") # Olie checkt mobiliteit
        else:
            # Metalen checken pH
            path.append("TestPH")
            if ph_val > 6.5:
                path.append("RouteHard")
                is_hard_route = True
            else:
                path.append("TestMob")
    
    # Als we nog niet op hard zitten, check mobiliteit
    if not is_hard_route:
        # Hier zou je user input kunnen vragen: "Is het mobiel?"
        # We nemen aan JA (dummy logica)
        is_mobiel = True 
        
        if not is_mobiel:
            path.append("RouteHard")
            is_hard_route = True
        else:
            path.append("TestPlant")
            # Check effectiviteit (daling per jaar > 1%)
            dalingen = pd.to_numeric(df['daling_jaar'], errors='coerce').fillna(0)
            max_daling = dalingen.max()
            
            if max_daling < 1:
                path.append("Stop1")
                return path
            else:
                path.append("RouteEasy")

    # --- STAP 4: TIJD CHECK ---
    path.append("TimeCheck")
    
    # Bereken max tijd (Dummy: 100 / daling snelheid)
    # We nemen alleen stoffen die reductie nodig hebben
    relevant = df[pd.to_numeric(df['reductie_lan'], errors='coerce') > 0].copy()
    relevant['snelheid'] = pd.to_numeric(relevant['daling_jaar'], errors='coerce')
    
    if not relevant.empty and relevant['snelheid'].max() > 0:
        relevant['jaren'] = relevant['reductie_lan'] / relevant['snelheid']
        max_jaren = relevant['jaren'].max()
    else:
        max_jaren = 99 # Oneindig als snelheid 0 is
        
    if max_jaren > 15 or is_hard_route:
        path.append("Feas")
        # Aanname: Additieven werken
        path.append("PilotAssist")
    else:
        path.append("PilotReg")
        
    return path

# --- DE APP START HIER ---
st.set_page_config(page_title="Bio2Clean Selector", layout="wide")

st.title("🌱 Bio2Clean Fyto-Selector")
st.markdown("Upload de Excel-analyse om de haalbaarheid en strategie te bepalen.")

# 1. FILE UPLOAD
uploaded_file = st.file_uploader("Upload Excel of CSV", type=['xlsx', 'csv'])

if uploaded_file is not None:
    # Parsing logica (Simpel gehouden voor demo)
    try:
        if uploaded_file.name.endswith('.csv'):
            raw_df = pd.read_csv(uploaded_file, header=None)
        else:
            raw_df = pd.read_excel(uploaded_file, header=None)
            
        # Simuleer data cleaning (Dit moet je tunen op jouw exacte bestand)
        # We maken even hardcoded dummy data op basis van je screenshot
        # zodat de app ALTIJD werkt voor deze demo.
        # IN PRODUCTIE: Haal dit uit 'raw_df'
        
        clean_df = pd.DataFrame({
            'stofnaam': ["Cadmium", "Kobalt", "Koper", "Kwik", "Lood", "Zink", "Olie C10-C40", "PAK"],
            'reductie_lan': [78, 0, 52, 82, 38, 59, 75, 67],
            'daling_jaar': [3, 1, 4, 1, 1, 4, 10, 1]
        })
        metadata = {'ph_kcl': 6.6}
        
        # Toon data samenvatting
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Gevonden Vervuiling")
            st.dataframe(clean_df)
        with col2:
            st.subheader("Metadata")
            st.write(f"**pH-KCl:** {metadata['ph_kcl']}")
            
        # 2. LOGICA UITVOEREN
        active_path = determine_path(clean_df, metadata)
        
        # 3. VISUALISATIE (Graphviz)
        st.subheader("Beslissingsboom Visualisatie")
        
        # Functie om kleur te bepalen
        def get_attr(node_name):
            if node_name in active_path:
                return 'fillcolor="gold", style="filled", penwidth=3'
            return 'style="filled", fillcolor="white"'

        # De Flowchart in DOT taal (Graphviz)
        # Dit lijkt op Mermaid, maar is standaard in Python packages
        graph = f"""
        digraph Fyto {{
            rankdir=TB;
            node [shape=box, fontname="Arial", fontsize=10];
            
            Start [label="Start: Analyse", {get_attr("Start")}];
            CheckLAN [label="Reductie > 50%?", shape=diamond, {get_attr("CheckLAN")}];
            
            PilotReg [label="Pilot: Regulier\\n(< 10 jaar)", fillcolor="lightgreen", style="filled", {("penwidth=3, color=darkgreen" if "PilotReg" in active_path else "")}];
            CheckType [label="Type Vervuiling?", shape=diamond, {get_attr("CheckType")}];
            
            Org [label="Check Fractie", {get_attr("Org")}];
            Met [label="Check Metalen", {get_attr("Met")}];
            Mix [label="Check Mix", {get_attr("Mix")}];
            
            RouteHard [label="Route: Complex\\n(Pb, Hg, Zware Olie)", fillcolor="mistyrose", style="filled", {("penwidth=3, color=red" if "RouteHard" in active_path else "")}];
            
            TestMob [label="Mobiel?", shape=diamond, {get_attr("TestMob")}];
            TestPH [label="pH > 6.5?", shape=diamond, {get_attr("TestPH")}];
            TestPlant [label="Opname meetbaar?", shape=diamond, {get_attr("TestPlant")}];
            
            Stop1 [label="STOP: Afvoeren", shape=octagon, fillcolor="salmon", style="filled", {("penwidth=3" if "Stop1" in active_path else "")}];
            RouteEasy [label="Route: Makkelijk", {get_attr("RouteEasy")}];
            
            TimeCheck [label="Tijd > 15jr?", shape=diamond, {get_attr("TimeCheck")}];
            Feas [label="Additieven OK?", shape=diamond, {get_attr("Feas")}];
            
            Stop2 [label="STOP: Afvoeren", shape=octagon, fillcolor="salmon", style="filled", {("penwidth=3" if "Stop2" in active_path else "")}];
            PilotAssist [label="Pilot: Assisted\\n(met Additieven)", fillcolor="lightyellow", style="filled", {("penwidth=3, color=orange" if "PilotAssist" in active_path else "")}];
            
            # Connecties
            Start -> CheckLAN;
            CheckLAN -> PilotReg [label=" Nee"];
            CheckLAN -> CheckType [label=" Ja"];
            
            CheckType -> Org;
            CheckType -> Met;
            CheckType -> Mix;
            
            Org -> RouteHard [label=" Zwaar"];
            Met -> RouteHard [label=" Pb/Hg"];
            Mix -> RouteHard [label=" Zwaar"];
            
            Org -> TestMob [label=" Licht"];
            Met -> TestPH [label=" Zn/Cd"];
            Mix -> TestPH [label=" Zn/Cd"];
            
            TestPH -> RouteHard [label=" Ja"];
            TestPH -> TestMob [label=" Nee"];
            
            TestMob -> RouteHard [label=" Nee"];
            TestMob -> TestPlant [label=" Ja"];
            
            TestPlant -> Stop1 [label=" Nee"];
            TestPlant -> RouteEasy [label=" Ja"];
            
            RouteHard -> TimeCheck;
            RouteEasy -> TimeCheck;
            
            TimeCheck -> PilotReg [label=" Nee"];
            TimeCheck -> Feas [label=" Ja"];
            
            Feas -> Stop2 [label=" Nee"];
            Feas -> PilotAssist [label=" Ja"];
        }}
        """
        
        st.graphviz_chart(graph)
        
        # Conclusie tekst
        st.info(f"**Conclusie:** Het pad eindigt bij **{active_path[-1]}**.")
        
    except Exception as e:
        st.error(f"Fout bij inlezen bestand: {e}")

else:
    st.info("Upload een bestand om te beginnen.")