# Análise Operacional com a metodologia Arcadia

## Referência conceitual aprofundada e base para um assistente de modelagem

**Versão:** 1.0  
**Data de consolidação:** 21 de agosto de 2026  
**Escopo:** Operational Analysis (OA) da metodologia Arcadia, com atenção à semântica necessária para uma base de conhecimento e para a validação assistida de modelos.  
**Idioma de trabalho:** português, mantendo os nomes oficiais dos conceitos em inglês quando isso reduz ambiguidade.

---

## 1. Finalidade e estatuto deste documento

Este documento tem duas finalidades complementares:

1. servir como material de ajuda aprofundado sobre a Análise Operacional em Arcadia; e
2. fornecer uma base textual controlada da qual se deriva uma ontologia consultável por software.

O texto não substitui o livro de referência de Jean-Luc Voirin, os documentos oficiais Arcadia nem a validação por especialistas do domínio. Ele consolida, organiza e interpreta essas fontes para uso em uma aplicação de apoio. A decisão final sobre a correção do modelo permanece com o usuário/modelador.

Para reduzir o risco de falsa autoridade, cada regra deste material pertence a uma destas categorias:

- **Referência Arcadia:** definição ou orientação sustentada diretamente pelos documentos de referência.
- **Boa prática de modelagem:** recomendação coerente com Arcadia, mas dependente do contexto.
- **Política da aplicação:** decisão implementável no software para ajudar o usuário; não deve ser apresentada como regra oficial da metodologia.
- **Heurística linguística:** indício extraído da forma da frase; nunca é prova semântica suficiente.

Essa distinção também existe na ontologia por meio da propriedade `oa:guidanceStatus`.

---

## 2. Base documental e confiabilidade

As fontes principais são documentos publicados pelo ecossistema oficial Eclipse Capella/Arcadia e assinados por Jean-Luc Voirin/Thales:

- [Arcadia — apresentação, princípios e perspectivas](https://mbse-capella.org/arcadia.html)
- [Arcadia User Guide (2023)](https://mbse-capella.org/resources/arcadia-reference/Arcadia%20User%20Guide.pdf)
- [Arcadia Reference — Engineering Data Model (2023)](https://mbse-capella.org/resources/arcadia-reference/Arcadia%20Reference%20-%20Data%20Model.pdf)
- [Arcadia Language — MetaModel (2023)](https://mbse-capella.org/resources/arcadia-reference/Arcadia%20Language%20-%20MetaModel.pdf)
- [Arcadia Reference — Workflow and Activities (2023)](https://mbse-capella.org/resources/arcadia-reference/Arcadia%20Reference%20-%20Activities.pdf)
- [Arcadia Questions & Answers, Jean-Luc Voirin/Thales (2023)](https://mbse-capella.org/resources/arcadia-reference/Arcadia%20Q%26A.pdf)
- [Página navegável Arcadia Questions & Answers](https://mbse-capella.org/arcadia-qna.html)
- [Livro de referência: *Model-based System and Architecture Engineering with the Arcadia Method*](https://www.iste.co.uk/book.php?id=1265)

Como apoio secundário e não como autoridade normativa principal, foram consultados materiais da comunidade Capella. Eles ajudam a esclarecer usos práticos, em especial a distinção entre Operational Entity e Operational Actor, mas qualquer divergência deve ser resolvida em favor dos documentos de referência:

- [Discussão Capella: Operational Analysis — Actors and Entities](https://forum.mbse-capella.org/t/operational-analysis-actors-and-entities/3065)
- [Discussão Capella: sistema de interesse na OA](https://forum.mbse-capella.org/t/model-system-under-study-in-operational-analysis/3004)
- [Discussão Capella: processos e capacidades operacionais](https://forum.mbse-capella.org/t/op-capability-involv-operational-processes/5092)

Para a arquitetura técnica do grafo foram usados padrões abertos:

- [RDF 1.2 Concepts — W3C](https://www.w3.org/TR/rdf12-concepts/)
- [SPARQL 1.1 Query Language — W3C](https://www.w3.org/TR/sparql11-query/)
- [SHACL — W3C](https://www.w3.org/TR/shacl/)
- [Structured Outputs — documentação oficial do Ollama](https://docs.ollama.com/capabilities/structured-outputs)

### Limite de interpretação

Os documentos Arcadia descrevem conceitos, relações e atividades, mas não entregam diretamente uma ontologia RDF/OWL pronta para esta aplicação. A ontologia anexa é, portanto, uma **formalização derivada**, com proveniência explícita. Ela preserva a semântica Arcadia quando sustentada pelas fontes e rotula extensões necessárias à aplicação.

---

## 3. Arcadia em contexto

Arcadia significa **ARChitecture Analysis and Design Integrated Approach**. É uma metodologia de engenharia baseada em modelos para definição e exploração colaborativa de arquiteturas de sistemas, software e hardware. Capella é a ferramenta e a linguagem de modelagem que dão suporte prático à metodologia; Arcadia não é apenas uma notação gráfica e Capella não deve ser confundida com a metodologia inteira.

As perspectivas centrais são:

1. **Operational Analysis (OA):** o que usuários e demais stakeholders precisam realizar no domínio operacional;
2. **System Need Analysis (SA):** o que o sistema deve fazer para contribuir com a necessidade operacional;
3. **Logical Architecture (LA):** como o sistema funcionará em uma solução nocional, independente de escolhas tecnológicas detalhadas;
4. **Physical Architecture (PA):** como a solução finalizada será estruturada e implementada;
5. **Building Strategy:** contratos e estrutura para desenvolvimento, integração e IVVQ.

As perspectivas não constituem obrigatoriamente uma sequência linear. Os documentos oficiais enfatizam iteração, realimentação e adaptação a fluxos top-down, bottom-up, middle-out, incrementais ou orientados a reúso. A relação entre atividades é principalmente uma dependência de consistência, não uma ordem temporal rígida.

### 3.1 Separação entre necessidade e solução

Uma regra de ouro de Arcadia é separar claramente necessidade e solução:

- OA e SA pertencem ao espaço da necessidade;
- LA e PA descrevem o espaço da solução;
- OA ainda não define a fronteira nem a responsabilidade do sistema de interesse;
- SA introduz o sistema, sua fronteira, seus atores externos e sua contribuição funcional.

Essa separação evita transformar uma necessidade em uma prescrição prematura de solução. Se o usuário precisa fixar um quadro, começar a OA pelo “uso da furadeira” já eliminou alternativas como adesivo, prego ou outro mecanismo. A formulação operacional deve explorar o resultado necessário, as condições, restrições, atores e critérios, antes de escolher o sistema que contribuirá para realizá-lo.

---

## 4. O que é a Análise Operacional em Arcadia

### 4.1 Definição

A Análise Operacional é a perspectiva que analisa as necessidades e os objetivos dos stakeholders, suas missões e atividades esperadas, geralmente antes e além dos requisitos textuais do cliente, sem considerar ainda a solução ou o sistema de interesse em si.

Seu principal produto é uma **arquitetura operacional**: uma descrição estruturada da necessidade em termos de entidades e atores, missões, capacidades, atividades, interações, processos, cenários, dados, meios de comunicação, modos, estados e restrições operacionais.

### 4.2 Objetivos de engenharia

Segundo o *Arcadia User Guide*, a OA deve contribuir para:

- compreender a necessidade real do cliente em termos de tarefas dos usuários;
- verificar consistência e completude da necessidade;
- produzir material para trade-offs, otimizações e negociações futuras;
- sustentar cenários e condições realistas de integração, verificação, validação e qualificação;
- revelar oportunidades, restrições, riscos, situações críticas e capacidades que os requisitos textuais podem não explicitar.

O maior valor está na palavra **análise**. Uma coleção de diagramas que apenas transcreve o que o cliente disse não alcança o objetivo. A formalização deve provocar perguntas, expor diferenças entre situações, identificar casos degradados e comparar expectativas conflitantes.

### 4.3 O que a OA não é

A OA não é:

- uma descrição da arquitetura do produto;
- uma decomposição do sistema em subsistemas;
- uma lista de funções do sistema;
- apenas um diagrama de contexto da fronteira do sistema;
- uma transcrição visual de requisitos existentes;
- uma tentativa de modelar exaustivamente toda a organização do cliente;
- um substituto de business analysis, design thinking, concept development, arquitetura empresarial ou análise de missão quando essas disciplinas forem necessárias.

### 4.4 Onde parar

Dois limites são essenciais:

1. **não introduzir o sistema de interesse como solução na OA**; e
2. **limitar a cobertura ao contexto que influencia a necessidade e a futura contribuição do sistema**.

Não é útil formalizar todo o material operacional. Textos, entrevistas e documentos podem continuar como fontes detalhadas, enquanto o modelo captura padrões representativos, situações dimensionantes, oportunidades, ameaças, restrições e relações necessárias à análise.

---

## 5. Abordagem recomendada para construir a OA

### 5.1 Começar pela história, não pelo diagrama

O Q&A oficial recomenda começar contando a história do trabalho, das expectativas e da vida operacional dos usuários e stakeholders. As fontes podem incluir:

- entrevistas;
- observação de operações atuais;
- conceitos de operação;
- requisitos e contratos;
- procedimentos e doutrina;
- relatos de incidentes;
- cenários de teste;
- modelos legados;
- análise de sistemas existentes e de capacidades atuais.

Perguntas iniciais úteis:

- Qual é a missão ou resultado maior?
- Quem participa, influencia ou é afetado?
- O que cada participante precisa realizar?
- O que inicia, facilita, restringe ou interrompe esse trabalho?
- Que informação, material, energia, sinal ou serviço precisa ser trocado?
- Que situações representam o caso nominal, o pior caso e o caso degradado?
- Que propriedade quantitativa torna a situação dimensionante?
- O que hoje funciona mal, é lento, perigoso, caro ou exige esforço excessivo?
- Que resultado permitirá dizer operacionalmente que a necessidade foi atendida?

### 5.2 Converter narrativa em conceitos

Após validar a narrativa com stakeholders, termos e relações candidatos são classificados como:

- missão;
- capacidade operacional;
- entidade ou ator operacional;
- atividade;
- interação e item trocado;
- processo;
- cenário;
- meio de comunicação;
- modo, estado ou situação;
- restrição ou parâmetro dimensionante;
- dado/conceito do domínio.

Essa classificação é uma hipótese de modelagem. A aplicação pode sugerir uma classe, mas deve apresentar sua justificativa e permitir que o usuário altere a decisão.

### 5.3 Iterar e validar

Uma sequência prática — não obrigatória — é:

1. delimitar propósito, stakeholders e fontes;
2. capturar missões e objetivos;
3. identificar capacidades e critérios;
4. identificar entidades, atores e estrutura organizacional relevante;
5. descrever atividades e responsabilidades;
6. ligar atividades por interações e conteúdos;
7. organizar caminhos significativos em processos;
8. descrever cenários temporais nominais, alternativos e degradados;
9. adicionar modos, estados, restrições e parâmetros;
10. verificar coerência interna e externa;
11. revisar com especialistas e stakeholders;
12. usar a OA para derivar perguntas da SA, sem copiar mecanicamente atividades como funções.

O critério oficial de parada da atividade de OA é obter concordância dos stakeholders de nível superior, incluindo o cliente quando possível, sobre a descrição da necessidade operacional. A ferramenta pode medir cobertura e consistência, mas não pode substituir essa concordância.

---

## 6. Conceitos fundamentais e sua semântica

## 6.1 Operational Mission

Uma **Operational Mission** é um objetivo de alto nível para o qual uma ou mais entidades operacionais devem contribuir e que pode influenciar a definição ou o uso do sistema futuro.

Uma missão responde principalmente a **por que** a organização atua. Ela é mais ampla que uma atividade e normalmente utiliza diversas capacidades.

Exemplos de forma, não de domínio obrigatório:

- garantir resposta coordenada a emergências;
- manter a circulação segura em determinada área;
- entregar assistência dentro de uma janela operacional.

Boas perguntas:

- A missão expressa um resultado organizacional de alto nível?
- Há entidades responsáveis por contribuir para ela?
- Quais capacidades precisam estar disponíveis?
- Existe critério que distingue sucesso, degradação e fracasso?

Antipadrões:

- nome de componente ou produto usado como missão;
- ação elementar apresentada como missão;
- missão sem stakeholder ou capacidade relacionada;
- slogan sem significado verificável.

## 6.2 Operational Capability

Uma **Operational Capability** é uma habilidade esperada de uma ou mais entidades operacionais para prestar um serviço que contribui para cumprir uma ou mais missões operacionais.

Ela organiza a análise por resultados e casos de uso. Pode ser descrita por vários processos e cenários; esses processos **descrevem** a capacidade, não são componentes que a “implementam”. A implementação/contribuição do sistema será tratada nas perspectivas seguintes.

Uma capacidade robusta deve explicitar, quando relevante:

- serviço ou resultado esperado;
- objeto ou beneficiário;
- condições de operação;
- medida ou nível de desempenho;
- prazo, distância, precisão, volume ou disponibilidade;
- entidades envolvidas;
- restrições críticas;
- cenários que mostram seu significado.

Exemplo de estrutura semântica:

> capacidade de [resultado/serviço] para [objeto/beneficiário], em [condição], com [critério quantitativo ou qualitativo].

O *User Guide* dá como exemplo uma capacidade mais informativa do que um verbo isolado: a habilidade de detectar/localizar determinado tipo de alvo em uma área e em menos de certo tempo. Isso mostra por que “detectar” sozinho pode ser insuficiente.

Antipadrões:

- capacidade escrita como solução técnica;
- capacidade idêntica a uma atividade elementar;
- capacidade sem missão ou stakeholder;
- capacidade sem cenário explicativo;
- capacidade sem condições que permitam diferenciar casos operacionais.

## 6.3 Operational Entity

Uma **Operational Entity** é uma entidade do mundo real ou stakeholder — por exemplo, elemento físico, grupo, organização ou outro sistema — que realiza atividades operacionais às quais o sistema futuro poderá contribuir ou que pode influenciar o sistema.

Entidades podem representar, conforme a necessidade da análise:

- organizações;
- equipes;
- unidades operacionais;
- instalações e nós geográficos relevantes;
- sistemas externos existentes no domínio operacional;
- elementos físicos ou objetos de interesse;
- ameaças ou entidades não cooperativas;
- ambiente quando ele tem comportamento ou propriedades relevantes para a análise.

Uma entidade não deve ser incluída apenas porque existe no mundo. Ela deve ter relevância para pelo menos uma missão, capacidade, atividade, interação, restrição, estado ou cenário.

### Decomposição e contenção

Entidades podem ser decompostas quando suas partes:

- realizam atividades distintas;
- mudam de estado de maneira independente;
- participam de cenários diferentes;
- precisam ser responsabilizadas separadamente;
- afetam decisões futuras de escopo ou alocação.

A ontologia representa essa relação por `oa:containsEntity`. Contenção deve significar uma relação operacional/organizacional relevante, não mera proximidade visual ou localização eventual.

### Instalações, áreas e infraestrutura

Uma instalação, edifício ou área pode ser Operational Entity quando é um elemento do mundo real que influencia ou participa do comportamento operacional. Porém, a classificação deve depender do papel semântico:

- se apenas caracteriza onde algo ocorre, pode ser melhor tratada como contexto/localização;
- se tem estado, restrições, recursos, responsabilidades ou interações que importam, pode justificar uma Operational Entity;
- se já é parte da solução a ser projetada, não deve ser introduzida como solução na OA.

Essa é uma decisão contextual, não uma classificação automática baseada no substantivo “edifício” ou “área”.

## 6.4 Operational Actor

Um **Operational Actor** é uma Operational Entity não decomponível, usualmente humana. Em Capella, ator operacional é uma especialização estrutural da entidade operacional.

Consequências:

- toda instância de Operational Actor também é Operational Entity;
- o ator pode realizar atividades, participar de capacidades e cenários e trocar itens;
- na OA, “actor” não deve ser confundido com “external actor” da SA;
- um departamento, empresa ou equipe costuma ser entidade, não ator humano indivisível;
- uma pessoa ou papel humano individual pode ser ator quando esse nível de detalhe é importante.

O termo “usualmente humano” permite que a fonte preserve alguma flexibilidade, mas a política recomendada para a aplicação é perguntar ao usuário quando algo não humano for classificado como Operational Actor. Para elementos não humanos decomponíveis, Operational Entity é normalmente mais claro.

### Papel versus pessoa

Em muitos modelos, o nome do ator representa um papel — “Operador”, “Piloto”, “Coordenador” — e não um indivíduo chamado João ou Maria. Isso favorece reutilização e análise de responsabilidades. Dados pessoais só devem aparecer se forem indispensáveis ao propósito do modelo.

## 6.5 Operational Activity

Uma **Operational Activity** é uma ação, operação ou serviço realizado por uma entidade operacional, capaz de influenciar a definição ou o uso do sistema futuro e de contribuir para uma missão.

Ela descreve **o que o stakeholder faz**, independentemente de qual parte será futuramente apoiada ou automatizada pelo sistema.

Convenção linguística útil:

- nomear com verbo no infinitivo + objeto/complemento;
- exemplos de forma: “avaliar solicitação”, “coordenar resposta”, “informar condição operacional”.

Essa convenção é uma heurística, não uma prova. Frases com vários verbos podem representar:

- uma atividade composta que precisa de decomposição;
- atividades coordenadas distintas;
- condição + ação;
- objetivo + meio;
- uma sequência que pertence melhor a um cenário/processo.

### Decomposição funcional

Atividades podem conter subatividades. A decomposição deve ser motivada por necessidade analítica, não por desejo de detalhar tudo. Critérios úteis:

- responsáveis diferentes;
- interações distintas;
- estados/modos distintos;
- restrições diferentes;
- participação diferente em processos ou cenários;
- necessidade de comparar alternativas ou alocação futura.

Boa prática: atividades não folha funcionam como agrupamentos; interações e responsabilidades devem ser levadas ao nível folha quando a análise detalhada exigir clareza.

## 6.6 Operational Interaction

Uma **Operational Interaction** é uma dependência possível entre duas atividades operacionais, uma fonte e uma destinatária, pela transmissão de elementos transportados na interação.

Ela responde:

- qual atividade fornece algo;
- qual atividade recebe ou usa esse algo;
- o que é transmitido;
- em que direção;
- sob quais condições e restrições.

O conteúdo pode representar informação, sinal, material, energia, solicitação ou outro item relevante ao domínio. A semântica deve estar no item trocado, não apenas em rótulos vagos como “dados” ou “informação”.

### Interação não é automaticamente controle temporal

O dataflow de Capella expressa dependência e troca, não uma semântica completa de execução. Uma seta entre atividades não prova, sozinha, que a primeira sempre ocorre antes da segunda. Ordem temporal pertence a processo, cenário e ocorrências explicitamente ordenadas.

Antipadrões:

- interação sem fonte ou destino;
- interação entre entidades sem atividades quando é necessário entender a responsabilidade comportamental;
- item trocado sem significado de domínio;
- inferir sequência obrigatória apenas pelo dataflow;
- usar meio de comunicação como se fosse o conteúdo trocado.

## 6.7 Interaction Item e Operational Data

Um **Interaction Item** descreve o conteúdo esperado de uma interação. Pode agrupar referências a dados ou conceitos do domínio que são transportados juntos.

**Operational Data** representa elementos das interações ou comunicações. Dados podem ser agrupados em itens de troca, e os itens são transportados pelas interações.

Exemplo de separação semântica:

- interação: “enviar avaliação de risco”;
- item: “Avaliação de risco”; 
- dados: nível, justificativa, timestamp, identificador da situação.

Essa separação permite validar completude, segurança, propriedade, qualidade e consistência do conteúdo sem confundir o fluxo com sua estrutura interna.

## 6.8 Communication Mean

Um **Communication Mean** é um suporte que liga duas entidades operacionais e habilita as interações entre elas.

Exemplos genéricos:

- voz presencial;
- rádio existente no ambiente;
- mensageria organizacional;
- transporte físico;
- canal institucional;
- procedimento formal de passagem de informação.

Na OA, o meio deve refletir o mundo operacional e suas restrições, sem impor prematuramente a tecnologia do sistema futuro. Um protocolo ou componente que será projetado pode pertencer à solução e, portanto, exigir tratamento em SA/LA/PA.

Distinção:

- **Operational Interaction:** dependência/troca entre atividades;
- **Interaction Item:** o que é trocado;
- **Communication Mean:** suporte entre entidades que permite a troca.

## 6.9 Operational Process

Um **Operational Process** é um conjunto ordenado de referências a atividades e às interações que as ligam, descrevendo um caminho possível no dataflow operacional. No *Engineering Data Model*, ele também é descrito como uma organização lógica de atividades e interações para cumprir uma capacidade.

Um processo:

- seleciona um caminho significativo no conjunto de atividades/interações;
- ajuda a explicar uma capacidade;
- pode ser reutilizado em mais de um contexto;
- não é um componente que implementa a capacidade;
- pode coexistir com outros processos que descrevem a mesma capacidade.

Processo e cenário não são sinônimos. O processo organiza um caminho lógico; o cenário descreve ocorrências e ordem temporal em uma situação específica.

## 6.10 Operational Scenario

Um **Operational Scenario** é um fluxo temporalmente ordenado de interações entre atividades ou entre entidades/atores no contexto de uma capacidade operacional.

Dois pontos de vista são comuns:

- **Operational Activity Scenario:** lifelines/ocorrências centradas nas atividades;
- **Operational Entity Scenario:** lifelines centradas nas entidades e atores.

Um cenário deve deixar claro:

- capacidade explicada;
- situação e precondições;
- participantes;
- sequência de ocorrências e interações;
- condições, alternativas, repetições e paralelismo quando relevantes;
- resultado esperado;
- parâmetros dimensionantes;
- modos e estados relevantes;
- exceções e resultado degradado.

É importante manter cenários “sunny day” e “rainy day”:

- **nominal:** uso esperado sem perturbação relevante;
- **alternativo:** variação ainda aceitável;
- **degradado:** capacidade reduzida ou recursos indisponíveis;
- **indesejado/temido:** situação a evitar, conter ou detectar;
- **limite/dimensionante:** caso que impõe desempenho, capacidade ou segurança.

Na ontologia, `ScenarioOccurrence` é uma extensão da aplicação para representar a repetição da mesma atividade em diferentes posições de um cenário sem confundir a atividade-tipo com sua ocorrência temporal.

## 6.11 Mode, State e Situation

Os documentos Arcadia distinguem:

- **Mode:** comportamento esperado/escolhido em certas condições;
- **State:** comportamento ou condição sofrida/imposta pelo ambiente;
- **Situation:** combinação de modos e estados por operadores lógicos.

Exemplos de forma:

- modo: operação manual, operação coordenada, fase de resposta;
- estado: disponível, degradado, indisponível, ambiente adverso;
- situação: “operação coordenada E canal degradado E baixa visibilidade”.

Modos e estados devem ser ligados à entidade apropriada e às atividades disponíveis/necessárias na condição. Não devem ser usados apenas como etiquetas decorativas.

## 6.12 Operational Constraint e Dimensioning Parameter

Uma **Operational Constraint** é uma expectativa ou condição que restringe elementos do modelo. Pode envolver:

- desempenho e latência;
- segurança (safety);
- cibersegurança e proteção;
- fatores humanos;
- disponibilidade e resiliência;
- ambiente;
- legislação e doutrina;
- custo de ciclo de vida;
- logística, implantação e sustentabilidade;
- competência e treinamento.

Um **Dimensioning Parameter** torna uma condição mensurável ou comparável: tempo máximo, volume simultâneo, distância, precisão, taxa, carga de trabalho, probabilidade, disponibilidade etc.

Uma restrição útil precisa indicar:

- elemento ao qual se aplica;
- condição de aplicabilidade;
- valor/unidade ou critério qualitativo controlado;
- origem e justificativa;
- criticidade/prioridade;
- cenário em que pode ser avaliada.

---

## 7. Relações essenciais da ontologia

| Origem | Relação | Destino | Semântica |
|---|---|---|---|
| Operational Mission | usesCapability | Operational Capability | A missão depende da disponibilidade da capacidade. |
| Operational Entity | involvedInCapability | Operational Capability | A entidade tem participação/interesse operacional na capacidade. |
| Operational Entity | performsActivity | Operational Activity | Responsabilidade pela realização da atividade. |
| Operational Entity | containsEntity | Operational Entity | Decomposição organizacional/física relevante. |
| Operational Activity | contributesToMission | Operational Mission | A atividade ajuda a alcançar a missão. |
| Operational Interaction | sourceActivity | Operational Activity | Atividade fornecedora. |
| Operational Interaction | targetActivity | Operational Activity | Atividade destinatária. |
| Operational Interaction | conveys | Interaction Item | Conteúdo transportado. |
| Communication Mean | connectsEntity | Operational Entity | Entidades ligadas pelo suporte de comunicação. |
| Operational Process | hasProcessElement | Activity/Interaction | Elementos que compõem um caminho operacional. |
| Operational Process | describesCapability | Operational Capability | O processo explica um caso da capacidade. |
| Operational Scenario | describesCapability | Operational Capability | O cenário explica dinamicamente a capacidade. |
| Operational Scenario | hasOccurrence | Scenario Occurrence | Ocorrência temporal no cenário. |
| Scenario Occurrence | occurrenceOf | Activity/Interaction | Tipo reutilizável que ocorre naquela posição. |
| Constraint | constrains | qualquer elemento aplicável | Condição que limita ou caracteriza o elemento. |
| Mode/State | enablesActivity | Operational Activity | Atividade disponível/necessária na condição. |

As cardinalidades rígidas devem ser usadas com cuidado. Durante a captura inicial, elementos incompletos são naturais. Por isso, as regras SHACL anexas separam:

- **Violation:** inconsistência estrutural que compromete o significado;
- **Warning:** lacuna importante a revisar;
- **Info:** melhoria recomendada.

---

## 8. Coerência, qualidade e completude

## 8.1 Coerência externa

O modelo deve ser confrontado com:

- documentos do cliente;
- entrevistas;
- requisitos;
- procedimentos;
- conceitos de operação;
- modelos anteriores;
- fatos e restrições do domínio.

Uma afirmação do modelo deve poder indicar sua fonte ou rationale. A ontologia permite anexar `prov:wasDerivedFrom`, `dcterms:source`, `oa:sourceLocator` e `oa:rationale`.

## 8.2 Coerência interna

Perguntas mínimas:

- toda capacidade contribui para alguma missão?
- toda capacidade possui entidades envolvidas e pelo menos um processo/cenário que a explique?
- toda atividade relevante tem performer?
- toda interação possui fonte e destino válidos?
- o performer da atividade fonte e o da atividade destino são compatíveis com o meio de comunicação?
- itens trocados têm significado e direção?
- processos usam atividades/interações conectadas?
- cenários têm ordem, participantes, capacidade e resultado?
- restrições estão anexadas aos elementos certos?
- o sistema de interesse foi introduzido indevidamente?
- há elementos órfãos ou duplicados semanticamente?
- nomes diferentes representam o mesmo conceito?
- o mesmo nome está sendo usado para conceitos diferentes?

## 8.3 Completude não é exaustividade

Completude significa cobertura suficiente para decisões e validação, não modelar tudo que existe. Um modelo pode ser enorme e ainda incompleto se omitir uma situação crítica; pode ser compacto e suficiente se capturar as diferenças que dirigem a solução.

## 8.4 Rastreabilidade sem cópia mecânica

OA e SA devem ser relacionadas, mas não copiadas mecanicamente:

- Operational Activity descreve o que o stakeholder faz;
- System Function descreve o que se espera do sistema ou de seus atores externos no escopo da SA;
- uma atividade pode ser apoiada por várias funções;
- uma função pode contribuir para várias atividades;
- algumas atividades continuarão exclusivamente humanas/organizacionais;
- uma interação operacional pode gerar funções internas, funções de interface e requisitos não funcionais.

---

## 9. Uso da ontologia como “help” da aplicação

## 9.1 O que pode ser respondido de forma controlada

O grafo pode responder perguntas como:

- “O que é uma Operational Capability?”
- “Qual a diferença entre Operational Actor e Operational Entity?”
- “O sistema de interesse deve aparecer na OA?”
- “Que elementos descrevem uma capacidade?”
- “Qual a diferença entre interação, item trocado e meio de comunicação?”
- “Que verificações devo executar antes de concluir a OA?”
- “Por que esta atividade foi marcada como órfã?”

Cada resposta deve retornar:

1. afirmações recuperadas do grafo;
2. o status de cada afirmação (referência, recomendação ou política);
3. fonte e localização;
4. explicação em linguagem natural;
5. grau de cobertura/confiança;
6. mensagem explícita quando a base não contiver resposta suficiente.

## 9.2 O que significa “não usar o conhecimento próprio da LLM”

Não é possível apagar o conhecimento aprendido durante o treinamento de uma LLM. É possível, entretanto, impedir que esse conhecimento seja aceito como evidência pelo sistema:

- a aplicação consulta o grafo antes de gerar a resposta;
- somente fatos retornados e identificados podem aparecer como afirmações factuais;
- o prompt proíbe completar lacunas;
- cada sentença material precisa citar IDs de evidência;
- um verificador checa se as citações realmente sustentam a sentença;
- sem evidência suficiente, a resposta padrão é “a base não contém informação suficiente”; 
- temperatura baixa e saída estruturada reduzem variação, mas não substituem verificação;
- perguntas determinísticas podem ser respondidas sem LLM, por templates.

A formulação correta é, portanto: **a LLM não é a fonte de verdade; o knowledge graph é a fonte autorizada, e a LLM apenas interpreta a pergunta e verbaliza resultados recuperados**.

## 9.3 Dois grafos separados

A arquitetura recomendada mantém:

- **Reference Graph:** conceitos, definições, regras, perguntas e fontes Arcadia;
- **Project Graph:** elementos criados pelo usuário e sua proveniência.

Eles compartilham a mesma ontologia, mas não o mesmo estatuto epistemológico. Isso evita que um exemplo ou uma hipótese do usuário seja apresentado como definição da metodologia.

## 9.4 Comparação com o modelo do usuário

A comparação deve combinar quatro mecanismos:

1. **validação estrutural SHACL:** cardinalidades, tipos, domínios, elementos órfãos;
2. **consultas SPARQL:** padrões de completude, cobertura e rastreabilidade;
3. **heurísticas linguísticas:** forma de nomes e frases, sempre como sugestão;
4. **revisão contextual:** perguntas ao usuário quando a semântica não puder ser decidida pelos dados.

Exemplos de achados:

- violação: interação sem atividade fonte;
- violação: elemento marcado como sistema de interesse na OA;
- aviso: capacidade sem cenário;
- aviso: atividade sem performer;
- aviso: ator operacional marcado como decomponível;
- informação: nome de atividade não começa por verbo reconhecido;
- pergunta contextual: “Edifício A” é apenas localização ou uma entidade com estado/atividade relevante?

## 9.5 Evitar que a LLM altere o modelo silenciosamente

Fluxo recomendado:

1. usuário fornece texto;
2. parser/LLM produz **candidatos**, não fatos aprovados;
3. schema JSON valida formato;
4. regras determinísticas detectam duplicidade e incompatibilidade;
5. aplicação mostra proposta, rationale e evidência;
6. usuário aprova, edita ou rejeita;
7. só então o Project Graph é atualizado;
8. mudança recebe autor, timestamp, fonte e versão;
9. validação é executada novamente.

---

## 10. Semântica linguística para extração assistida

## 10.1 Sujeito, verbo e objeto como ponto de partida

Uma frase simples pode ser mapeada como:

- sujeito → candidato a entidade/ator;
- verbo → candidato a atividade ou relação;
- objeto → candidato a entidade, item de interação ou dado;
- complemento circunstancial → condição, local, tempo, restrição ou parâmetro.

Exemplo abstrato:

> “O coordenador envia a prioridade à equipe em até dois minutos.”

Candidatos:

- Coordenador: Operational Actor;
- Equipe: Operational Entity;
- Enviar prioridade: Operational Activity ou Interaction, dependendo do modelo;
- Prioridade: Interaction Item/Data;
- até dois minutos: Constraint/Dimensioning Parameter.

Mas o padrão SVO é insuficiente para frases reais.

## 10.2 Vários verbos

> “A equipe avalia o incidente, define a prioridade e informa o coordenador.”

Pode produzir três atividades coordenadas, com um possível processo. A aplicação deve preservar a frase original e propor a divisão, não impor a divisão.

## 10.3 Vários sujeitos

> “O operador e o supervisor confirmam a autorização.”

Hipóteses:

- uma atividade com coparticipação;
- duas atividades semelhantes com responsabilidades distintas;
- uma entidade composta;
- regra de dupla autorização.

Somente o contexto decide.

## 10.4 Voz passiva e sujeito oculto

> “A solicitação é validada antes do despacho.”

Há uma atividade candidata, mas o performer está ausente. O software deve criar uma lacuna/pergunta, não inventar o responsável.

## 10.5 Nominalização

> “Validação da solicitação pelo supervisor.”

“Validação” é substantivo, mas semanticamente indica uma atividade. Heurísticas precisam reconhecer nominalizações sem transformar todo substantivo abstrato em ação.

## 10.6 Modalidade e negação

> “A equipe deve confirmar o alerta, mas não pode divulgar a localização.”

- “deve” pode indicar obrigação/requisito;
- “não pode” indica proibição;
- não se deve criar a atividade “divulgar localização” como comportamento permitido sem registrar a negação.

## 10.7 Condição e exceção

> “Se o canal principal estiver indisponível, o operador usa o canal alternativo.”

O conteúdo envolve estado, condição, atividade, meio alternativo e cenário degradado. Reduzir a frase a uma tripla perde parte essencial do significado.

## 10.8 Regra geral para extração

O extrator deve produzir estruturas com:

- trecho original;
- candidatos e tipos possíveis;
- relações candidatas;
- qualificadores de negação, modalidade, condição e tempo;
- confiança por campo;
- rationale;
- questões em aberto;
- identificação do método (regra, parser ou LLM);
- tempo de processamento.

---

## 11. Regras de aceitação por conceito

### Operational Entity

Aceitar quando:

- representa elemento real/stakeholder relevante;
- possui papel operacional claro;
- participa de atividade, capacidade, cenário, interação ou restrição;
- não é apenas o sistema de interesse disfarçado.

Perguntar quando:

- é apenas lugar ou objeto passivo;
- mistura organização, papel e indivíduo;
- parece uma tecnologia escolhida para a solução.

### Operational Actor

Aceitar quando:

- é entidade operacional não decomponível, usualmente humana;
- seu papel individual é relevante para a análise.

Perguntar quando:

- representa equipe/departamento;
- foi decomposto;
- é não humano sem justificativa.

### Operational Activity

Aceitar quando:

- expressa ação/operação/serviço do stakeholder;
- possui performer conhecido ou lacuna explicitamente registrada;
- contribui para missão/capacidade/processo/cenário.

Perguntar quando:

- contém várias ações independentes;
- descreve função do sistema;
- é apenas objetivo, dado ou entidade.

### Operational Interaction

Aceitar quando:

- possui atividade fonte e destino;
- direção e conteúdo são compreensíveis;
- não é apenas uma associação genérica.

Perguntar quando:

- conteúdo ou direção não está claro;
- fonte e destino são a mesma atividade sem justificativa;
- pretende expressar apenas ordem temporal.

### Operational Capability

Aceitar quando:

- expressa habilidade/serviço orientado a resultado;
- envolve entidades;
- contribui para missão;
- tem processo ou cenário explicativo;
- contém critérios quando necessários.

Perguntar quando:

- é apenas um verbo genérico;
- já prescreve tecnologia;
- não há diferença observável entre sucesso e fracasso.

### Communication Mean

Aceitar quando:

- é suporte operacional entre entidades;
- habilita interações identificadas;
- é relevante para restrições, disponibilidade ou desempenho.

Perguntar quando:

- é item/conteúdo, não meio;
- é tecnologia futura da solução;
- não conecta entidades relevantes.

---

## 12. Padrões de perguntas para o assistente

O assistente deve perguntar uma questão por vez e explicar por que pergunta. Exemplos:

- “Qual resultado de alto nível essa capacidade ajuda a atingir?”
- “Quem executa esta atividade hoje, independentemente do sistema futuro?”
- “O edifício realiza/influencia algum comportamento ou é apenas a localização da atividade?”
- “O que exatamente é transferido nesta interação?”
- “Este canal já existe no domínio operacional ou é parte da solução que será projetada?”
- “Que condição torna este cenário diferente do caso nominal?”
- “Qual valor ou critério permite avaliar se a capacidade foi alcançada?”
- “Esse nome representa uma equipe decomponível ou um papel humano individual?”
- “Esta segunda ação deve ser uma atividade separada?”
- “Quem é o responsável pela ação escrita na voz passiva?”

As respostas “não sei”, “a definir”, “pular” e “não aplicável” devem ser preservadas com significados distintos. “Não sei” gera lacuna; “não aplicável” precisa de justificativa; “pular” adia a pergunta sem responder.

---

## 13. Anti-alucinação e governança

### 13.1 Proveniência em nível de afirmação

Cada definição ou regra deve armazenar:

- ID estável;
- texto da afirmação;
- fonte;
- seção/página ou URL;
- status epistemológico;
- data de consulta;
- versão;
- responsável pela curadoria.

### 13.2 Não misturar exemplo e regra

Exemplos servem para ilustrar uma definição; não devem virar regras de domínio. “Piloto é ator” não significa que todo papel humano será necessariamente modelado naquele nível. “Rádio é meio” não significa que toda comunicação precise de rádio.

### 13.3 Resposta com cobertura explícita

Estados recomendados:

- `SUPPORTED`: resposta integralmente sustentada;
- `PARTIALLY_SUPPORTED`: parte sustentada, parte ausente;
- `NOT_FOUND`: nada suficiente na base;
- `CONFLICTING_EVIDENCE`: fontes ou regras aplicáveis entram em conflito;
- `NEEDS_DOMAIN_DECISION`: metodologia permite alternativas e falta contexto.

### 13.4 Atualização controlada

Nova documentação não deve ser ingerida automaticamente como verdade. Fluxo:

1. importar como fonte candidata;
2. extrair afirmações candidatas;
3. comparar com a versão atual;
4. revisão humana;
5. aprovar/rejeitar;
6. publicar nova versão do Reference Graph;
7. executar regressão de consultas e regras.

---

## 14. Conclusão

É tecnicamente e metodologicamente adequado usar um knowledge graph para apoiar sua aplicação de Análise Operacional. O grafo pode cumprir dois papéis:

- **base de ajuda controlada**, respondendo perguntas com definições e orientações rastreáveis;
- **motor de consistência**, comparando os elementos do usuário com tipos, relações e regras de qualidade.

A LLM local via Ollama deve permanecer na periferia do mecanismo de verdade: interpretar linguagem natural, sugerir candidatos e redigir respostas. RDF/SPARQL/SHACL, regras determinísticas, proveniência e aprovação do usuário formam o núcleo confiável.

O resultado não é uma “IA que conhece Arcadia por si mesma”, mas um assistente que **consulta uma base Arcadia explícita, mostra sua evidência, reconhece lacunas e mantém o usuário como autoridade final do modelo**.

