import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
import time
from supabase import create_client, Client
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO
from datetime import datetime
from PIL import Image

# --- 1. CONFIGURAÇÃO COM ÍCONE DE INSTALAÇÃO ---
st.set_page_config(page_title="AEE Conecta", layout="centered", page_icon="logo.png")

# Esse bloco reforça para o Windows/Android/iPhone qual imagem usar no ícone de atalho
st.markdown(
    """
    <head>
        <meta name="google" content="notranslate">
        <link rel="icon" href="https://raw.githubusercontent.com/marcoshgomes/aee-conecta/main/logo.png">
        <link rel="apple-touch-icon" href="https://raw.githubusercontent.com/marcoshgomes/aee-conecta/main/logo.png">
        <link rel="shortcut icon" href="https://raw.githubusercontent.com/marcoshgomes/aee-conecta/main/logo.png">
    </head>
    <script>
        document.documentElement.lang = 'pt-br';
        document.documentElement.classList.add('notranslate');
    </script>
    """,
    unsafe_allow_html=True
)

# --- 2. CONEXÃO SUPABASE ---
try:
    URL = st.secrets["supabase"]["url"]
    KEY = st.secrets["supabase"]["key"]
    supabase: Client = create_client(URL, KEY)
except:
    st.error("Erro nas credenciais do Supabase no arquivo secrets.toml.")
    st.stop()

# Garantir pastas locais
if not os.path.exists("fotos_alunos"): os.makedirs("fotos_alunos")

# --- 3. FUNÇÕES DE APOIO ---
def hash_pw(senha):
    return hashlib.sha256(str(senha).encode()).hexdigest()

def registrar_log(rf):
    try:
        supabase.table("logs").insert({"rf": rf, "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')}).execute()
    except:
        pass

def load_professores():
    try:
        res = supabase.table("professores").select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

def load_estudantes():
    try:
        res = supabase.table("estudantes").select("*").execute()
        return pd.DataFrame(res.data)
    except:
        return pd.DataFrame()

# --- 4. FUNÇÕES DE GERAÇÃO DE WORD ---
def gerar_folha_rosto(dados):
    doc = Document()
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run("CEU EMEF Prof.ª MARA CRISTINA TARTAGLIA SENA\nAEE - ATENDIMENTO EDUCACIONAL ESPECIALIZADO\nREGISTRO - ATIVIDADE FLEXIBILIZADA").bold = True
    doc.add_paragraph(f"ANO LETIVO {datetime.now().year}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    if dados.get('foto_path'):
        try:
            res_foto = supabase.storage.from_("fotos_perfil").download(dados['foto_path'])
            doc.add_picture(BytesIO(res_foto), width=Inches(2.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except:
            pass

    t = doc.add_table(rows=4, cols=1); t.style = 'Table Grid'
    t.rows[0].cells[0].text = f"ESTUDANTE: {dados.get('aluno', 'N/A')}"
    t.rows[1].cells[0].text = f"TURMA: {dados.get('turma', 'N/A')}"
    col_nec = next((x for x in list(dados.index) if "nec" in x), "necessidades")
    t.rows[2].cells[0].text = f"DEFICIÊNCIA/CONDIÇÃO: {dados.get(col_nec, 'N/A')}"
    t.rows[3].cells[0].text = f"DATA DE NASCIMENTO: {dados.get('data_nascimento', 'N/A')}"
    
    doc.add_heading('PERFIL E OBSERVAÇÕES DO PROFESSOR PAEE:', level=3)
    doc.add_paragraph(str(dados.get('observacoes_gerais', '')))
    
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf

def gerar_relatorio_aula(df_rels, nome_aluno, turma_aluno, df_professores):
    doc = Document()
    for i, row in df_rels.iterrows():
        rf_aula = row['rf_professor']
        filtro_p = df_professores[df_professores['rf'] == rf_aula]
        nome_p = filtro_p.iloc[0]['nome'] if not filtro_p.empty else "Professor não identificado"

        h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.add_run("CEU EMEF Prof.ª MARA CRISTINA TARTAGLIA SENA\nAEE - ATENDIMENTO EDUCACIONAL ESPECIALIZADO\nREGISTRO - ATIVIDADE FLEXIBILIZADA").bold = True
        p_title = doc.add_paragraph(); p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_title.add_run(f"{row['bimestre']} – ANO LETIVO {datetime.now().year}").bold = True
        
        doc.add_paragraph(f"ESTUDANTE: {nome_aluno}\nTURMA: {turma_aluno}")
        doc.add_paragraph(f"PROFESSOR: {nome_p} | DISCIPLINA/TEMA: {row.get('disciplina_tema', 'N/A')}")
        
        p_sim = "x" if row.get('participou_aula') == "Sim" else " "
        p_nao = "x" if row.get('participou_aula') == "Não" else " "
        txt_part = doc.add_paragraph(f"O ESTUDANTE PARTICIPOU DA SUA AULA? ( {p_sim} ) SIM ( {p_nao} ) NÃO.")
        if row.get('participou_aula') == "Não":
            txt_part.add_run(f" RELATE O MOTIVO: {row.get('motivo_nao_participou', '')}")
            
        doc.add_heading('ATIVIDADES PLANEJADAS:', level=3); doc.add_paragraph(str(row['planejado']))
        doc.add_heading('ATIVIDADE REALIZADA COM O ESTUDANTE:', level=3); doc.add_paragraph(str(row['realizado']))
        
        if row['foto_path']:
            try:
                res_foto = supabase.storage.from_("fotos_aee").download(row['foto_path'])
                doc.add_picture(BytesIO(res_foto), width=Inches(3.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except: pass
        
        doc.add_heading('COMO FOI A PARTICIPAÇÃO DO ESTUDANTE?', level=3)
        parts = str(row['participacao']).split(", ")
        opcoes = ["REALIZOU COM AUTONOMIA", "REALIZOU COM APOIO E INTERVENÇÃO DE UM ADULTO", "REALIZOU WITH APOIO DE UM COLEGA", "NÃO REALIZOU"]
        for op in opcoes:
            check = "x" if op in parts else " "
            doc.add_paragraph(f"( {check} ) {op}")
        
        doc.add_paragraph(f"\nDATA DE REALIZAÇÃO DA ATIVIDADE: {row['data']}")
        if i < len(df_rels) - 1: doc.add_page_break()
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf

# --- 5. LÓGICA DE LOGIN ---
df_prof = load_professores()

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "change_pw" not in st.session_state: st.session_state.change_pw = False

if not st.session_state.logged_in:
    st.title("💠 AEE Conecta - Login")
    rf_in = st.text_input("RF").strip()
    pw_in = st.text_input("Senha", type="password").strip()

    if st.button("Entrar"):
        if df_prof.empty:
            supabase.table("professores").insert({"rf": rf_in, "nome": "Gestor Mestre", "perfil": "gestao"}).execute()
            st.rerun()
        
        user_db = df_prof[df_prof['rf'] == rf_in]
        if not user_db.empty:
            res_creds = supabase.table("credenciais").select("senha_hash").eq("rf", rf_in).execute()
            
            if not res_creds.data:
                if pw_in == rf_in:
                    st.session_state.change_pw, st.session_state.temp_rf = True, rf_in
                    st.rerun()
                else:
                    st.warning("Primeiro acesso? Use seu RF como senha.")
            else:
                if hash_pw(pw_in) == res_creds.data[0]['senha_hash']:
                    st.session_state.logged_in, st.session_state.u_rf = True, rf_in
                    st.session_state.u_nome = user_db.iloc[0]['nome']
                    st.session_state.u_perfil = str(user_db.iloc[0]['perfil']).lower().strip().replace('çã', 'ca')
                    registrar_log(rf_in); st.rerun()
                else:
                    st.error("Senha incorreta.")
        else:
            st.error("Usuário não cadastrado.")

    if st.session_state.change_pw:
        st.divider()
        st.warning("⚠️ CADASTRE UMA SENHA PESSOAL")
        n_pw = st.text_input("Nova Senha (min. 6 carac.)", type="password")
        c_pw = st.text_input("Confirme a Senha", type="password")
        if st.button("Salvar Nova Senha"):
            if len(n_pw) >= 6 and n_pw == c_pw:
                supabase.table("credenciais").insert({"rf": st.session_state.temp_rf, "senha_hash": hash_pw(n_pw)}).execute()
                st.session_state.change_pw = False
                st.toast("✅ Senha cadastrada!")
                time.sleep(1.5); st.rerun()
            else:
                st.error("Verifique os dados.")

else:
    # --- 6. INTERFACE LOGADA ---
    df_alunos = load_estudantes()
    st.sidebar.title(f"Olá, {st.session_state.u_nome}")
    menu = st.sidebar.radio("Navegação", ["Início", "Lançar Relatório", "Painel de Documentos", "Sair"])
    if menu == "Sair": st.session_state.logged_in = False; st.rerun()
    super_perfis = ["gestao", "gestor", "paee", "direcao", "coordenador"]

    # --- INÍCIO ---
    if menu == "Início":
        st.title("🏠 Bem-vindo ao AEE Conecta")
        st.markdown(f"### Olá, {st.session_state.u_nome}!")
        st.divider()
        st.info("""
        Este sistema foi desenvolvido para simplificar o registro e a gestão dos atendimentos do AEE.
        
        **Como utilizar:**
        *   **Professores:** Utilize o menu ao lado e clique em **Lançar Relatório** para registrar suas aulas.
        *   **Gestores/PAEE:** Acesse o **Painel de Documentos** para baixar Folhas de Rosto e gerenciar perfis.
        
        *Dica: No celular, você pode usar o microfone do teclado para ditar os textos das atividades!*
        """)
        st.success("Selecione uma opção no menu lateral para começar.")
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='text-align: center; color: #888888; font-size: 0.9em; border-top: 1px solid #eeeeee; padding-top: 20px;'>
                <b>By Prof. Marcão</b><br>
                Software de apoio pedagógico - Freeware
            </div>
            """,
            unsafe_allow_html=True
        )

    # --- LANÇAR RELATÓRIO ---
    elif menu == "Lançar Relatório":
        st.header("📝 Lançar Relatório de Aula")
        if df_alunos.empty: st.warning("Aguardando cadastro de alunos.")
        else:
            if "form_id" not in st.session_state: st.session_state.form_id = 0
            
            # --- INÍCIO DA CORREÇÃO ---
            # Criamos a coluna de exibição Nome - Turma
            df_alunos['exibicao'] = df_alunos['aluno'] + " - " + df_alunos['turma']
            lista_est = ["Selecione o Estudante..."] + sorted(df_alunos['exibicao'].tolist())
            
            # O seletor usa a coluna 'exibicao'
            al_sel_visual = st.selectbox("Escolha o aluno:", lista_est, key=f"sel_{st.session_state.form_id}")

            if al_sel_visual != "Selecione o Estudante...":
                # Extraímos o nome puro antes do " - " para buscar os dados no banco
                nome_puro = al_sel_visual.split(" - ")[0]
                al_inf = df_alunos[df_alunos['aluno'] == nome_puro].iloc[0]
                # --- FIM DA CORREÇÃO ---
                
                with st.container(border=True):
                    st.subheader(f"Aluno: {nome_puro}")
                    dt = st.date_input("Data", datetime.now()); bm = st.selectbox("Bimestre", ["1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                    tm = st.text_input("Disciplina ou Tema"); p_a = st.radio("Participou?", ["Sim", "Não"], horizontal=True)
                    mot = st.text_area("Se 'Não', motivo:") if p_a == "Não" else ""; pl = st.text_area("Atividades Planejadas"); re = st.text_area("Atividades Realizadas")
                    pn = st.multiselect("Nível:", ["REALIZOU COM AUTONOMIA", "APOIO ADULTO", "APOIO COLEGA", "NÃO REALIZOU"])
                    ft = st.file_uploader("Foto opcional")
                    if st.button("Salvar Relatório"):
                        p_f = ""
                        if ft:
                            p_f = f"aula_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                            supabase.storage.from_("fotos_aee").upload(p_f, ft.getvalue())
                        supabase.table("relatorios").insert({"data": dt.strftime('%d/%m/%Y'), "rf_professor": st.session_state.u_rf, "registro_aluno": str(al_inf['registro']), "bimestre": bm, "participou_aula": p_a, "motivo_nao_participou": mot, "disciplina_tema": tm, "planejado": pl, "realizado": re, "participacao": ", ".join(pn), "foto_path": p_f}).execute()
                        st.toast("✅ Relatório salvo!"); time.sleep(1.5); st.session_state.form_id += 1; st.rerun()

    # --- PAINEL DE DOCUMENTOS ---
    elif menu == "Painel de Documentos":
        st.title("📂 Painel de Documentos")
        list_tabs = ["📄 Documentos"]
        if st.session_state.u_perfil in super_perfis: 
            list_tabs += ["👤 Gestão de Alunos", "👥 Gestão de Professores", "🔒 Segurança e Monitoramento"]
        abas = st.tabs(list_tabs)
        
        with abas[0]: # ABA DOCUMENTOS
            if df_alunos.empty: st.info("Sem alunos cadastrados.")
            else:
                # --- INÍCIO DA CORREÇÃO ---
                df_alunos['exibicao'] = df_alunos['aluno'] + " - " + df_alunos['turma']
                al_f_visual = st.selectbox("Selecione o Aluno", sorted(df_alunos['exibicao'].tolist()), key="gest_sel")
                
                # Pega o nome puro para não dar erro de NameError nas variáveis abaixo
                al_f_nome = al_f_visual.split(" - ")[0]
                d_f = df_alunos[df_alunos['aluno'] == al_f_nome].iloc[0]
                
                c1, c2 = st.columns(2)
                # Aqui usamos al_f_nome para o nome do arquivo .docx
                c1.download_button("📥 Baixar Folha de Rosto", gerar_folha_rosto(d_f), f"Rosto_{al_f_nome}.docx")
                # --- FIM DA CORREÇÃO ---
                
                query = supabase.table("relatorios").select("*").eq("registro_aluno", str(d_f['registro']))
                if st.session_state.u_perfil not in super_perfis: query = query.eq("rf_professor", st.session_state.u_rf)
                res_rels = query.execute(); df_res = pd.DataFrame(res_rels.data)
                if not df_res.empty:
                    bim_f = st.selectbox("Filtrar por Bimestre", ["Todos", "1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                    if bim_f != "Todos": df_res = df_res[df_res['bimestre'] == bim_f]
                    if not df_res.empty: 
                        # Corrigido o download usando o nome puro
                        c2.download_button(f"📥 Baixar Relatórios ({len(df_res)})", gerar_relatorio_aula(df_res, al_f_nome, d_f['turma'], df_prof), f"Relatorios_{al_f_nome}.docx")
                else: st.warning("Sem relatórios sob sua responsabilidade para este aluno.")

        if st.session_state.u_perfil in super_perfis:
            with abas[1]: # ABA GESTÃO DE ALUNOS
                st.subheader("Gestão de Alunos")
                
                # --- NOVO: Controle de reset para limpar a tela ---
                if "al_form_id" not in st.session_state: 
                    st.session_state.al_form_id = 0
                
                # A key dinâmica no radio e no form garante a limpeza total
                modo_a = st.radio("Ação Estudante:", ["Novo", "Editar/Excluir"], horizontal=True, key=f"modo_al_{st.session_state.al_form_id}")
                
                al_edit = None
                if modo_a == "Editar/Excluir" and not df_alunos.empty:
                    # Aqui também usamos o Nome + Turma para facilitar a vida da PAEE
                    df_alunos['exibicao_gestao'] = df_alunos['aluno'] + " - " + df_alunos['turma']
                    sel_a_visual = st.selectbox("Escolha o aluno para carregar os dados:", sorted(df_alunos['exibicao_gestao'].tolist()), key=f"sel_edit_al_{st.session_state.al_form_id}")
                    nome_puro_edit = sel_a_visual.split(" - ")[0]
                    al_edit = df_alunos[df_alunos['aluno'] == nome_puro_edit].iloc[0]
                
                # O formulário ganha uma key que muda a cada salvamento
                with st.form(key=f"f_aluno_{st.session_state.al_form_id}"):
                    reg = st.text_input("Registro (ID)", value=al_edit['registro'] if al_edit is not None else "")
                    nom = st.text_input("Nome Completo", value=al_edit['aluno'] if al_edit is not None else "")
                    tur = st.text_input("Turma", value=al_edit['turma'] if al_edit is not None else "")
                    nec = st.text_area("Condição/Deficiência", value=al_edit['necessidades'] if al_edit is not None else "")
                    nas = st.text_input("Nascimento (DD/MM/AAAA)", value=al_edit['data_nascimento'] if al_edit is not None else "")
                    obs = st.text_area("Observações Perfil", value=al_edit['observacoes_gerais'] if al_edit is not None else "")
                    ft_p = st.file_uploader("Foto Perfil", type=['png', 'jpg', 'jpeg'])
                    
                    c1, c2 = st.columns(2)
                    
                    if c1.form_submit_button("💾 Salvar Perfil"):
                        if modo_a == "Novo" and not df_alunos[df_alunos['registro'] == reg].empty:
                            st.error("⚠️ Este Registro já existe!"); st.stop()
                        
                        p_path = al_edit['foto_path'] if al_edit is not None else ""
                        if ft_p:
                            p_path = f"perfil_{reg}.png"
                            supabase.storage.from_("fotos_perfil").upload(p_path, ft_p.getvalue(), {"upsert": "true"})
                        
                        supabase.table("estudantes").upsert({
                            "registro": reg, "aluno": nom, "turma": tur, 
                            "necessidades": nec, "data_nascimento": nas, 
                            "observacoes_gerais": obs, "foto_path": p_path
                        }).execute()
                        
                        st.toast("✅ Perfil salvo com sucesso!")
                        # --- O PULO DO GATO: Incrementa o ID e reinicia ---
                        st.session_state.al_form_id += 1
                        time.sleep(1)
                        st.rerun()

                    if modo_a == "Editar/Excluir" and c2.form_submit_button("❌ EXCLUIR ALUNO"):
                        if al_edit['foto_path']: 
                            supabase.storage.from_("fotos_perfil").remove([al_edit['foto_path']])
                        supabase.table("estudantes").delete().eq("registro", al_edit['registro']).execute()
                        
                        st.toast("⚠️ Aluno removido!")
                        st.session_state.al_form_id += 1
                        time.sleep(1)
                        st.rerun()

                    if modo_a == "Editar/Excluir" and c2.form_submit_button("❌ EXCLUIR ALUNO"):
                        if al_edit['foto_path']: 
                            supabase.storage.from_("fotos_perfil").remove([al_edit['foto_path']])
                        supabase.table("estudantes").delete().eq("registro", al_edit['registro']).execute()
                        
                        st.toast("⚠️ Aluno removido!")
                        st.session_state.al_form_id += 1
                        time.sleep(1)
                        st.rerun()

            with abas[2]: # GESTÃO DE PROFESSORES
                st.subheader("Gerenciar Usuários")
                if "p_form_id" not in st.session_state: st.session_state.p_form_id = 0
                modo_p = st.radio("Ação:", ["Novo", "Editar/Excluir"], horizontal=True, key=f"mp_{st.session_state.p_form_id}")
                perfis_op = ["professor", "paee", "direcao", "coordenador"]
                if st.session_state.u_perfil == "gestao": perfis_op.append("gestao")
                
                if modo_p == "Novo":
                    with st.form(key=f"fn_{st.session_state.p_form_id}"):
                        nr = st.text_input("RF")
                        nn = st.text_input("Nome")
                        np = st.selectbox("Perfil", perfis_op)
                        if st.form_submit_button("Cadastrar Professor"):
                            if not nr or not nn:
                                st.error("Preencha o RF e o Nome.")
                            elif not df_prof[df_prof['rf'] == nr].empty:
                                st.error("⚠️ Este RF já está cadastrado!")
                            else:
                                supabase.table("professores").insert({"rf": nr, "nome": nn, "perfil": np}).execute()
                                st.toast("✅ Professor cadastrado!")
                                st.session_state.p_form_id += 1
                                time.sleep(1); st.rerun()
                else:
                    l_edit = sorted(df_prof['nome'].tolist()) if st.session_state.u_perfil == "gestao" else sorted(df_prof[df_prof['perfil'] != 'gestao']['nome'].tolist())
                    if not l_edit: st.info("Sem professores para edição.")
                    else:
                        psn = st.selectbox("Professor para editar:", l_edit)
                        psd = df_prof[df_prof['nome'] == psn].iloc[0]
                        with st.form(f"fe_{psn}"):
                            st.text_input("RF (Fixo)", value=psd['rf'], disabled=True)
                            en, ep = st.text_input("Nome", value=psd['nome']), st.selectbox("Perfil", perfis_op, index=perfis_op.index(psd['perfil']) if psd['perfil'] in perfis_op else 0)
                            c_b1, c_b2 = st.columns(2)
                            if c_b1.form_submit_button("Atualizar"): supabase.table("professores").update({"nome": en, "perfil": ep}).eq("rf", psd['rf']).execute(); st.rerun()
                            if c_b2.form_submit_button("❌ EXCLUIR"):
                                supabase.table("professores").delete().eq("rf", psd['rf']).execute(); st.rerun()

            with abas[3]: # SEGURANÇA E MONITORAMENTO
                st.subheader("Ferramentas de Gestão")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    l_reset = sorted(df_prof['nome'].tolist()) if st.session_state.u_perfil == "gestao" else sorted(df_prof[df_prof['perfil'] != 'gestao']['nome'].tolist())
                    pr = st.selectbox("Resetar Professor:", l_reset, key="rs")
                    if st.button("Resetar Senha"):
                        rr = df_prof[df_prof['nome'] == pr].iloc[0]['rf']
                        supabase.table("credenciais").delete().eq("rf", rr).execute(); st.warning("Resetado.")
                    
                    st.divider()
                    if st.button("📊 Gerar Relatório de Monitoramento"):
                        r_rels = supabase.table("relatorios").select("*").execute()
                        if r_rels.data:
                            m = pd.DataFrame(r_rels.data).merge(df_prof[['rf', 'nome']], left_on='rf_professor', right_on='rf', how='left').merge(df_alunos[['registro', 'aluno', 'turma']], left_on='registro_aluno', right_on='registro', how='left')
                            m = m[['nome_y', 'aluno', 'turma', 'data', 'bimestre']]; m.columns = ['Professor', 'Aluno', 'Turma', 'Data', 'Bimestre']
                            out = BytesIO(); m.to_excel(out, index=False); st.download_button("Download Excel", out.getvalue(), "monitor.xlsx")
                with col_s2:
                    if st.session_state.u_perfil == "gestao":
                        st.error("🚨 RESET TOTAL")
                        if st.button("🚨 ZERAR TUDO"): st.session_state.conf_res = True
                        if st.session_state.get("conf_res") and st.button("SIM, APAGAR SISTEMA"):
                            supabase.table("relatorios").delete().neq("id", -1).execute()
                            supabase.table("logs").delete().neq("id", -1).execute()
                            supabase.table("credenciais").delete().neq("rf", "xxx").execute()
                            supabase.table("estudantes").delete().neq("registro", "xxx").execute()
                            supabase.table("professores").delete().neq("rf", "xxx").execute()
                            st.session_state.logged_in = False; st.rerun()