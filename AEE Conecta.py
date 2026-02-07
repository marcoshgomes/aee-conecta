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
# Essa linha garante que o navegador veja o logo.png como o ícone da aba e do app
st.set_page_config(page_title="AEE Conecta", layout="centered", page_icon="logo.png")

# O código abaixo blinda o site contra o tradutor e reforça o ícone para o celular (PWA)
st.markdown(
    """
    <head>
        <meta name="google" content="notranslate">
        <link rel="apple-touch-icon" href="https://raw.githubusercontent.com/marcoshgomes/aee-conecta/main/logo.png">
        <link rel="icon" href="https://raw.githubusercontent.com/marcoshgomes/aee-conecta/main/logo.png">
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
    st.error("Erro nas credenciais do Supabase.")
    st.stop()

if not os.path.exists("fotos_alunos"): os.makedirs("fotos_alunos")

# --- 3. FUNÇÕES DE APOIO ---
def hash_pw(senha):
    return hashlib.sha256(str(senha).encode()).hexdigest()

def registrar_log(rf):
    try: supabase.table("logs").insert({"rf": rf, "data_hora": datetime.now().strftime('%d/%m/%Y %H:%M:%S')}).execute()
    except: pass

def load_professores():
    try:
        res = supabase.table("professores").select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

def load_estudantes():
    try:
        res = supabase.table("estudantes").select("*").execute()
        return pd.DataFrame(res.data)
    except: return pd.DataFrame()

# --- 4. FUNÇÕES DE WORD ---
def gerar_folha_rosto(dados):
    doc = Document()
    h = doc.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run("CEU EMEF Prof.ª MARA CRISTINA TARTAGLIA SENA\nAEE - ATENDIMENTO EDUCACIONAL ESPECIALIZADO\nREGISTRO - ATIVIDADE FLEXIBILIZADA").bold = True
    doc.add_paragraph(f"ANO LETIVO {datetime.now().year}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    if dados.get('foto_path'):
        try:
            res_foto = supabase.storage.from_("fotos_perfil").download(dados['foto_path'])
            doc.add_picture(BytesIO(res_foto), width=Inches(2.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except: pass
    t = doc.add_table(rows=4, cols=1); t.style = 'Table Grid'
    t.rows[0].cells[0].text = f"ESTUDANTE: {dados.get('aluno', 'N/A')}"
    t.rows[1].cells[0].text = f"TURMA: {dados.get('turma', 'N/A')}"
    col_nec = next((x for x in list(dados.index) if "nec" in x), "necessidades")
    t.rows[2].cells[0].text = f"DEFICIÊNCIA/CONDIÇÃO: {dados.get(col_nec, 'N/A')}"
    t.rows[3].cells[0].text = f"DATA DE NASCIMENTO: {dados.get('data_nascimento', 'N/A')}"
    doc.add_heading('PERFIL E OBSERVAÇÕES DO PROFESSOR PAEE:', level=3); doc.add_paragraph(str(dados.get('observacoes_gerais', '')))
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
        doc.add_paragraph(f"ESTUDANTE: {nome_aluno}\nTURMA: {turma_aluno}\nPROFESSOR: {nome_p} | TEMA: {row.get('disciplina_tema', 'N/A')}")
        part_sim, part_nao = ("x", " ") if row.get('participou_aula') == "Sim" else (" ", "x")
        doc.add_paragraph(f"O ESTUDANTE PARTICIPOU? ( {part_sim} ) SIM ( {part_nao} ) NÃO. {row.get('motivo_nao_participou', '')}")
        doc.add_heading('PLANEJADO:', level=3); doc.add_paragraph(str(row['planejado']))
        doc.add_heading('REALIZADO:', level=3); doc.add_paragraph(str(row['realizado']))
        if row['foto_path']:
            try:
                res_foto = supabase.storage.from_("fotos_aee").download(row['foto_path'])
                doc.add_picture(BytesIO(res_foto), width=Inches(3.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except: pass
        doc.add_heading('PARTICIPAÇÃO:', level=3); parts = str(row['participacao']).split(", ")
        for op in ["REALIZOU COM AUTONOMIA", "REALIZOU COM O APOIO DE UM ADULTO", "REALIZOU COM O APOIO DE UM COLEGA", "NÃO REALIZOU"]:
            check = "x" if op in parts else " "
            doc.add_paragraph(f"( {check} ) {op}")
        doc.add_paragraph(f"\nDATA: {row['data']}")
        if i < len(df_rels) - 1: doc.add_page_break()
    buf = BytesIO(); doc.save(buf); buf.seek(0); return buf

# --- 5. LOGIN ---
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
            st.success("Gestor Mestre criado! Use seu RF nos dois campos."); time.sleep(2); st.rerun()
        user_db = df_prof[df_prof['rf'] == rf_in]
        if not user_db.empty:
            res = supabase.table("credenciais").select("senha_hash").eq("rf", rf_in).execute()
            if not res.data:
                if pw_in == rf_in: st.session_state.change_pw, st.session_state.temp_rf = True, rf_in; st.rerun()
                else: st.warning("Primeiro acesso? Use o RF como senha.")
            else:
                if hash_pw(pw_in) == res.data[0]['senha_hash']:
                    st.session_state.logged_in, st.session_state.u_rf, st.session_state.u_nome = True, rf_in, user_db.iloc[0]['nome']
                    st.session_state.u_perfil = str(user_db.iloc[0]['perfil']).lower().strip().replace('çã', 'ca')
                    registrar_log(rf_in); st.rerun()
                else: st.error("Senha incorreta.")
        else: st.error("Usuário não cadastrado.")
    if st.session_state.change_pw:
        n_pw = st.text_input("Nova Senha (min. 6 carac.)", type="password")
        if st.button("Salvar Nova Senha"):
            if len(n_pw) >= 6:
                supabase.table("credenciais").insert({"rf": st.session_state.temp_rf, "senha_hash": hash_pw(n_pw)}).execute()
                st.session_state.change_pw = False; st.toast("✅ Salvo!"); time.sleep(1.5); st.rerun()
else:
    # --- 6. INTERFACE LOGADA ---
    df_alunos = load_estudantes()
    st.sidebar.title(f"Olá, {st.session_state.u_nome}")
    menu = st.sidebar.radio("Navegação", ["Início", "Lançar Relatório", "Painel de Documentos", "Sair"])
    if menu == "Sair": st.session_state.logged_in = False; st.rerun()
    super_perfis = ["gestao", "gestor", "paee", "direcao", "coordenador"]

    # --- TELA INICIAL (RESTAURADA) ---
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

    elif menu == "Lançar Relatório":
        st.header("📝 Lançar Relatório")
        if df_alunos.empty: st.warning("Aguardando cadastro de alunos.")
        else:
            if "form_id" not in st.session_state: st.session_state.form_id = 0
            lista = ["Selecione o Estudante..."] + sorted(df_alunos['aluno'].tolist())
            al_sel = st.selectbox("Escolha o aluno:", lista, key=f"sel_{st.session_state.form_id}")
            if al_sel != "Selecione o Estudante..." and not df_alunos.empty:
                al_inf = df_alunos[df_alunos['aluno'] == al_sel].iloc[0]
                with st.container(border=True):
                    dt = st.date_input("Data", datetime.now()); bm = st.selectbox("Bimestre", ["1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                    tm = st.text_input("Disciplina/Tema"); p_a = st.radio("Participou?", ["Sim", "Não"], horizontal=True)
                    mot = st.text_area("Se 'Não', motivo:") if p_a == "Não" else ""; pl = st.text_area("Planejado"); re = st.text_area("Realizado")
                    pn = st.multiselect("Nível:", ["REALIZOU COM AUTONOMIA", "REALIZOU COM O APOIO DE UM ADULTO", "REALIZOU COM O APOIO DE UM COLEGA", "NÃO REALIZOU"])
                    ft = st.file_uploader("Foto Aula")
                    if st.button("Salvar Registro"):
                        p_f = ""
                        if ft:
                            p_f = f"aula_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                            supabase.storage.from_("fotos_aee").upload(p_f, ft.getvalue())
                        supabase.table("relatorios").insert({"data": dt.strftime('%d/%m/%Y'), "rf_professor": st.session_state.u_rf, "registro_aluno": str(al_inf['registro']), "bimestre": bm, "participou_aula": p_a, "motivo_nao_participou": mot, "disciplina_tema": tm, "planejado": pl, "realizado": re, "participacao": ", ".join(pn), "foto_path": p_f}).execute()
                        st.toast("✅ Salvo!"); time.sleep(1.5); st.session_state.form_id += 1; st.rerun()

    elif menu == "Painel de Documentos":
        st.title("📂 Painel de Documentos")
        list_tabs = ["📄 Documentos"]
        if st.session_state.u_perfil in super_perfis: list_tabs += ["👤 Alunos", "👥 Professores", "🔒 Segurança"]
        abas = st.tabs(list_tabs)
        
        with abas[0]: # ABA DOCUMENTOS
            if df_alunos.empty: st.info("Sem alunos.")
            else:
                al_f = st.selectbox("Aluno", sorted(df_alunos['aluno'].tolist()), key="g_sel")
                d_f = df_alunos[df_alunos['aluno'] == al_f].iloc[0]
                c1, c2 = st.columns(2)
                c1.download_button("📥 Folha de Rosto", gerar_folha_rosto(d_f), f"Rosto_{al_f}.docx")
                query = supabase.table("relatorios").select("*").eq("registro_aluno", str(d_f['registro']))
                if st.session_state.u_perfil not in super_perfis: query = query.eq("rf_professor", st.session_state.u_rf)
                df_res = pd.DataFrame(query.execute().data)
                if not df_res.empty:
                    bim_f = st.selectbox("Bimestre", ["Todos", "1º Bimestre", "2º Bimestre", "3º Bimestre", "4º Bimestre"])
                    if bim_f != "Todos": df_res = df_res[df_res['bimestre'] == bim_f]
                    if not df_res.empty: c2.download_button(f"📥 Baixar Relatórios ({len(df_res)})", gerar_relatorio_aula(df_res, al_f, d_f['turma'], df_prof), f"Relatos_{al_f}.docx")

        if st.session_state.u_perfil in super_perfis:
            with abas[1]: # ABA GESTÃO DE ALUNOS
                st.subheader("Gestão de Alunos")
                modo_a = st.radio("Ação Estudante:", ["Novo", "Editar/Excluir"], horizontal=True)
                al_edit = None
                if modo_a == "Editar/Excluir" and not df_alunos.empty:
                    sel_a = st.selectbox("Selecione:", sorted(df_alunos['aluno'].tolist()))
                    al_edit = df_alunos[df_alunos['aluno'] == sel_a].iloc[0]
                with st.form("f_al"):
                    reg = st.text_input("Registro", value=al_edit['registro'] if al_edit is not None else "")
                    nom = st.text_input("Nome", value=al_edit['aluno'] if al_edit is not None else "")
                    tur = st.text_input("Turma", value=al_edit['turma'] if al_edit is not None else "")
                    nec = st.text_area("Condição", value=al_edit['necessidades'] if al_edit is not None else "")
                    nas = st.text_input("Nascimento", value=al_edit['data_nascimento'] if al_edit is not None else "")
                    obs = st.text_area("Observações Perfil", value=al_edit['observacoes_gerais'] if al_edit is not None else "")
                    ft_p = st.file_uploader("Foto Perfil")
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Salvar Aluno"):
                        p_path = al_edit['foto_path'] if al_edit is not None else ""
                        if ft_p:
                            p_path = f"perfil_{reg}.png"
                            supabase.storage.from_("fotos_perfil").upload(p_path, ft_p.getvalue(), {"upsert": "true"})
                        supabase.table("estudantes").upsert({"registro": reg, "aluno": nom, "turma": tur, "necessidades": nec, "data_nascimento": nas, "observacoes_gerais": obs, "foto_path": p_path}).execute()
                        st.success("Salvo!"); time.sleep(1); st.rerun()
                    if modo_a == "Editar/Excluir" and c2.form_submit_button("❌ EXCLUIR ALUNO"):
                        if al_edit['foto_path']: supabase.storage.from_("fotos_perfil").remove([al_edit['foto_path']])
                        supabase.table("estudantes").delete().eq("registro", al_edit['registro']).execute(); st.rerun()

            with abas[2]: # ABA GESTÃO DE PROFESSORES
                st.subheader("Gerenciar Usuários (Professores)")
                
                # --- TRECHO CORRIGIDO PARA LIMPAR A TELA ---
                if "p_form_id" not in st.session_state: 
                    st.session_state.p_form_id = 0
                
                modo_p = st.radio("Ação:", ["Novo", "Editar/Excluir"], horizontal=True, key=f"modo_p_{st.session_state.p_form_id}")
                
                perfis_opcoes = ["professor", "paee", "direcao", "coordenador"]
                if st.session_state.u_perfil == "gestao": perfis_opcoes.append("gestao")

                if modo_p == "Novo":
                    # O segredo é usar o p_form_id na key do formulário
                    with st.form(key=f"form_novo_prof_{st.session_state.p_form_id}"):
                        nr = st.text_input("RF")
                        nn = st.text_input("Nome")
                        np = st.selectbox("Perfil", perfis_opcoes)
                        
                        if st.form_submit_button("Cadastrar Professor"):
                            if nr and nn:
                                supabase.table("professores").insert({"rf": nr, "nome": nn, "perfil": np}).execute()
                                st.toast("✅ Professor cadastrado com sucesso!")
                                # Incrementa o ID para resetar todos os campos na volta
                                st.session_state.p_form_id += 1
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Preencha o RF e o Nome.")
                # --- FIM DO TRECHO DE CADASTRO NOVO ---
                
                else:
                    if st.session_state.u_perfil == "gestao":
                        lista_prof_edit = sorted(df_prof['nome'].tolist())
                    else:
                        lista_prof_edit = sorted(df_prof[df_prof['perfil'] != 'gestao']['nome'].tolist())
                    
                    if not lista_prof_edit: 
                        st.info("Sem professores para edição.")
                    else:
                        psn = st.selectbox("Professor:", lista_prof_edit)
                        psd = df_prof[df_prof['nome'] == psn].iloc[0]
                        with st.form(key=f"form_edit_prof_{psn}"):
                            st.text_input("RF (Fixo)", value=psd['rf'], disabled=True)
                            en = st.text_input("Nome", value=psd['nome'])
                            ep = st.selectbox("Perfil", perfis_opcoes, index=perfis_opcoes.index(psd['perfil']) if psd['perfil'] in perfis_opcoes else 0)
                            c_b1, c_b2 = st.columns(2)
                            if c_b1.form_submit_button("Atualizar Dados"):
                                supabase.table("professores").update({"nome": en, "perfil": ep}).eq("rf", psd['rf']).execute()
                                st.toast("✅ Atualizado!")
                                time.sleep(1)
                                st.rerun()
                            if c_b2.form_submit_button("❌ EXCLUIR"):
                                supabase.table("professores").delete().eq("rf", psd['rf']).execute()
                                supabase.table("credenciais").delete().eq("rf", psd['rf']).execute()
                                st.toast("❌ Removido!")
                                time.sleep(1)
                                st.rerun()

            with abas[3]: # ABA SEGURANÇA E MONITORAMENTO
                st.subheader("Segurança e Monitoramento")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    if st.session_state.u_perfil == "gestao": lista_prof_reset = sorted(df_prof['nome'].tolist())
                    else: lista_prof_reset = sorted(df_prof[df_prof['perfil'] != 'gestao']['nome'].tolist())
                    pr = st.selectbox("Resetar Professor:", lista_prof_reset, key="rs")
                    rr = df_prof[df_prof['nome'] == pr].iloc[0]['rf']
                    if st.button("Resetar Senha"):
                        supabase.table("credenciais").delete().eq("rf", rr).execute(); st.warning("Resetado.")
                    if st.button("📊 Monitoramento Excel"):
                        res_rels = supabase.table("relatorios").select("*").execute()
                        if res_rels.data:
                            m1 = pd.DataFrame(res_rels.data).merge(df_prof[['rf', 'nome']], left_on='rf_professor', right_on='rf', how='left')
                            m2 = m1.merge(df_alunos[['registro', 'aluno', 'turma']], left_on='registro_aluno', right_on='registro', how='left')
                            m2 = m2[['nome_y', 'aluno', 'turma', 'data', 'bimestre']]
                            m2.columns = ['Professor', 'Aluno', 'Turma', 'Data', 'Bimestre']
                            out = BytesIO(); m2.to_excel(out, index=False); st.download_button("Download Excel", out.getvalue(), "monitor.xlsx")
                with col_s2:
                    if st.session_state.u_perfil == "gestao":
                        st.error("🚨 ÁREA CRÍTICA")
                        if st.button("🚨 RESET TOTAL"): st.session_state.confirm_reset = True
                        if st.session_state.get("confirm_reset"):
                            if st.button("SIM, APAGAR TUDO"):
                                supabase.table("relatorios").delete().neq("id", -1).execute()
                                supabase.table("logs").delete().neq("id", -1).execute()
                                supabase.table("credenciais").delete().neq("rf", "xxx").execute()
                                supabase.table("estudantes").delete().neq("registro", "xxx").execute()
                                supabase.table("professores").delete().neq("rf", "xxx").execute()

                                st.error("Resetado!"); time.sleep(2); st.session_state.logged_in = False; st.rerun()
