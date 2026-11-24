# Termos de Uso

**Última atualização:** 23/11/2026

Estes termos valem para o uso do **J.A.R.V.I.S.** (o "JARVIS"), software de código aberto mantido por Felipe Grolla Freitas (o "desenvolvedor"). Ao instalar, executar ou usar o JARVIS, você concorda com eles. Se não concordar, não use. Eles são complementados pela [Política de Privacidade](politica-de-privacidade.md).

## Em resumo

- O JARVIS roda **no seu computador**. Não há conta, servidor do desenvolvedor nem cobrança.
- Ele pode **agir no seu PC** (abrir e fechar programas, enviar e-mail, instalar software…). Ações críticas pedem sua confirmação, e **o que você confirma é responsabilidade sua**.
- A IA é local e **pode errar**. Confira antes de confiar, principalmente em assuntos de saúde, dinheiro, lei e segurança.
- É oferecido **como está**, sem garantia, sob a licença MIT.

## 1. O que é o JARVIS

Um assistente pessoal para **Windows**, com interface de terminal (TUI), que conversa por texto (modo Chat) ou por voz (modo Copilot), usa um modelo de linguagem local (Ollama), guarda memória em SQLite e no seu vault do Obsidian e executa ações por meio de skills. O projeto está em **desenvolvimento ativo**: recursos mudam, e a branch `DEV` pode ser instável (veja [`SECURITY.md`](../SECURITY.md)).

## 2. Licença

O código é distribuído sob a **licença MIT** ([`LICENSE`](../LICENSE)): você pode usar, copiar, modificar e distribuir o software, mantendo o aviso de copyright. Estes termos regulam o **uso** do JARVIS e não restringem os direitos que a licença MIT dá sobre o código. Em caso de conflito sobre o código, vale a licença MIT.

## 3. Requisitos e contas de terceiros

- O **Ollama** e o modelo de IA são instalados por você. Cada modelo tem a **própria licença**, que você deve respeitar.
- Integrações opcionais (Google Agenda e Gmail, Spotify, GitHub, TomTom, Telegram, Discord) exigem **suas próprias contas e chaves**. Cada pessoa cria o próprio app OAuth ([`integracoes-oauth.md`](integracoes-oauth.md)). O repositório não traz chave nenhuma.
- Você deve cumprir os **termos de cada serviço** que conectar (limites de uso, automação, proibições). O JARVIS **não é afiliado** a esses serviços.
- O JARVIS é gratuito. Eventuais custos ou limites de serviços de terceiros ficam por sua conta.

## 4. Ações no seu computador

Dependendo das skills ativas e do modo, o JARVIS pode: abrir, focar e fechar programas; encerrar processos; controlar volume, teclado, mouse, janelas e abas do navegador; instalar ou baixar programas pelo winget; criar issues no GitHub; ler, rascunhar e enviar e-mails, organizar com marcadores e mover para a Lixeira do Gmail; bloquear IPs no Firewall do Windows; limpar arquivos do sistema; ligar o modo Não Perturbe; criar lembretes e gravar notas no Obsidian.

- **Ações críticas** (encerrar processo, enviar e-mail, apagar, instalar, bloquear IP, criar issue) mostram o que será feito e **só executam com a sua confirmação explícita** dentro do prazo. Silêncio, tempo esgotado ou uma frase que não seja confirmação **não aprovam** nada.
- **Leia antes de confirmar.** Quem confirma assume a ação. Não responda "sim" por hábito.
- No modo **Chat**, skills de automação e de sistema **não executam**. Você pode desligar skills e categorias inteiras em `/skills`.
- Apagar e-mail move para a **Lixeira** (recuperável por 30 dias). O JARVIS não faz exclusão permanente.

## 5. As respostas da IA podem errar

O modelo roda localmente e pode ser pequeno. Ele pode **inventar fatos, interpretar mal um pedido** ou entender errado o que você falou (o reconhecimento de voz também erra). Não use o JARVIS como **única base** para decisões médicas, jurídicas, financeiras, de segurança ou qualquer decisão com consequência relevante. Verifique as informações importantes na fonte.

## 6. Uso aceitável

Você concorda em:

1. Usar o JARVIS de acordo com a lei e com os direitos de outras pessoas.
2. **Não** acessar contas, dispositivos, redes ou dados de terceiros sem autorização.
3. **Não vigiar pessoas sem consentimento.** Microfone, leitura de tela, histórico do clipboard, leitura de e-mail e Vigia de rede podem alcançar dados de outras pessoas. Avise quem está no ambiente.
4. Na **ponte Telegram/Discord**, liberar só IDs de pessoas de confiança. Você responde pelo que essas pessoas pedem ao JARVIS. A lista vazia não libera ninguém.
5. **Não** usar o JARVIS para spam, assédio, fraude, violação de direitos autorais ou qualquer atividade ilegal.
6. **Não** contornar as confirmações e proteções de segurança para causar dano a você ou a terceiros.

## 7. Serviços de terceiros

Recursos online (voz, clima, trânsito, busca, notícias, Google, Spotify, GitHub, Telegram, Discord, winget, atualizações) enviam dados a terceiros, conforme a [Política de Privacidade](politica-de-privacidade.md). Esses serviços podem mudar, limitar, cobrar ou deixar de existir, e o recurso correspondente pode parar de funcionar. O desenvolvedor não controla nem garante esses serviços.

## 8. Atualizações

Na versão instalada, o JARVIS **verifica** se há versão nova nos Releases do GitHub (opção ligada por padrão, que você desliga em `/config` → SISTEMA). A instalação só começa **depois da sua confirmação**, e o instalador baixado tem o SHA-256 e a assinatura (Minisign) conferidos — sem assinatura válida ele não roda. A atualização substitui a versão anterior do programa; seus dados não são o alvo dela.

## 9. Suas chaves e a sua conta do Windows

- Guarde o seu `.env` (que pode ter chaves e tokens em texto) e a pasta de dados. **Nunca os envie a repositórios nem os compartilhe.**
- Os tokens das integrações OAuth ficam no **Cofre de Credenciais do Windows**. Quem acessa a sua conta do Windows pode usar o JARVIS e as integrações conectadas.
- Vazou uma chave ou token? **Revogue-a** no serviço de origem. Prejuízos por vazamento são de responsabilidade de quem guardou a chave.
- Achou uma vulnerabilidade? **Não abra issue pública.** Use o canal privado descrito em [`SECURITY.md`](../SECURITY.md).

## 10. Sem garantia

O JARVIS é fornecido **"como está"**, sem garantia de qualquer tipo, expressa ou implícita: funcionamento ininterrupto, ausência de erros, adequação a um fim específico, precisão das respostas ou disponibilidade das integrações.

## 11. Limitação de responsabilidade

Na máxima extensão permitida pela lei, o desenvolvedor e os contribuidores **não respondem** por danos indiretos, lucros cessantes, perda ou corrupção de dados, custos de serviços de terceiros, indisponibilidade, ações confirmadas por você (e-mail enviado ou apagado, programa instalado ou encerrado) nem por decisões tomadas com base em respostas da IA. Nada nestes termos exclui uma responsabilidade que a lei não permite excluir.

**Mantenha backup** do seu vault do Obsidian, da pasta de dados e de tudo que for importante.

## 12. Propriedade intelectual e marcas

- O código segue a licença MIT. O que **você** cria (conversas, notas, lembretes) é seu.
- "J.A.R.V.I.S." é uma homenagem ao personagem de ficção. O projeto é **independente** e não tem relação com Marvel, Disney, Google, Microsoft, Spotify, GitHub, Telegram, Discord, Ollama ou qualquer outra empresa citada. Nomes e marcas pertencem aos seus donos.

## 13. Encerramento

Você pode parar de usar o JARVIS quando quiser: desinstale e apague a pasta de dados e as notas que ele criou no vault. O desenvolvedor pode alterar, suspender ou descontinuar o projeto ou qualquer recurso a qualquer momento.

## 14. Mudanças nestes termos

Estes termos podem ser atualizados. A versão vigente é a deste arquivo no repositório, com a data no topo, e o histórico fica no git. Continuar usando o JARVIS depois de uma atualização significa aceitar a nova versão.

## 15. Lei aplicável e contato

Aplica-se a **legislação brasileira**. Dúvidas e bugs: abra uma issue no repositório do projeto. Vulnerabilidades: [`SECURITY.md`](../SECURITY.md) (canal privado). Mantenedor: Felipe Grolla Freitas ([@Grolla05](https://github.com/Grolla05)).
