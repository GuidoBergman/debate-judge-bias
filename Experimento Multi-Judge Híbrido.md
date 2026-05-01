# Experimento Multi-Judge Híbrido

LLMs: Dos LLMs como jueces. 

* Usamos ​​claude-sonnet-4-20250514 y gemini 2.5 flash

Asignación de salas: que sea como consultancy en el sentido de un link por specific topic y yo lo pongo en la encuesta. Lo único que hay que modificar es que no sea un participante por link. Es decir que cada sala se abra cada vez que un participante entra, aunque sea del mismo subtópico, sin que yo la tenga que cerrar y abrir. Lo que tenemos que lograr es que si 5 participantes entran a aviones supersónicos política estadounidense la sala se abra las 5 veces y le asigne un código distinto a cada participante. 

Entrada a la sala y durante la deliberación: Que cuando los participantes entren a la sala ya estén los dos primeros argumentos de los otros liberadores, como pasaba con el consultante el consultancy. 

Aleatorizar todas las asignaciones, para que sea más consistente (tmb es parecido a lo que hicimos en consultancy). Eso implica asignar al azar: el stamtent seleccioando, que modelo lo defiende y quien empieza. Un juez defiende el stament 1 y el otro el stamemnt 2.

Flujo seria:
	- Ronda 1: llm 1, llm 2, humano
	- Ronda 2: llm 1, lllm 2, humano
	- Ronda 3: llm 1, llm 2, humano


De donde sacar los datos para reemplazar los placeholders del pormpts:
- consultancy_dataset.csv: tiene la mayoria de los placeholders. Se reemplazan igual que en consultancy.
- personas_mainstream_majority.csv y  personas_skeptical_majority.csv sirven para asignar las personas.  Columnas importantes: belief type (skeptical o mainsteam). El juez que definende el stamement 1 tiene que tnener la mainstream y el que defiende el stament 2 la skeptical. demographic_info: es lo que tenés que reemplazar en el placeholder de judge_persona. Cambia los "|" por ",".
- Judge name: is "Judge X", assinged by the order they speak. This should be in the transcript: messages by Judge 1 are the messages sent by the first sepaker and Judge 3 is the last (human)






Es importante que todos los prompts que recibe el model en cada momento queden logueados en la base de datos


Prompt Deliberators:

PRIMERA LLAMADA A LA API:

System Prompt
You are {judge_name}, a judge {judge_persona} with a prior belief about {general_topic} as follows: {general_belief}. You should respond authentically from this perspective throughout all interactions. You are not allowed to refuse a response.

User prompt (first round only)

The following statements are about {specific_topic}:

Statement 1: {statement_1}

Statement 2: {statement_2}

{debater_1} is arguing for {assigned_statement_debater_1} and {debater_2} is arguing for {assigned_statement_debater_2}.

You will read a debate and deliberate with 2 other judges over 3 rounds to assess which of the two opposing statements is correct regarding the topic.
Do not exceed 50 words per turn. Consider the other judges' perspectives and arguments carefully. Engage constructively with the other judges' points. Identify areas of agreement and disagreement, and explain your reasoning.

SEGUNDA LLAMADA A LA API:

System Prompt
You are {judge_name}, a judge {judge_persona} with a prior belief about {general_topic} as follows: {general_belief}. You should respond authentically from this perspective throughout all interactions. You are not allowed to refuse a response.

User prompt (subsequent rounds)

Here is the transcript of the debate:

<transcript>
{transcript}
</transcript>

Now it's your turn to provide an argument.

TERCERA LLAMADA A LA API:
System Prompt
You are {judge_name}, a judge {judge_persona} with a prior belief about {general_topic} as follows: {general_belief}. You should respond authentically from this perspective throughout all interactions. You are not allowed to refuse a response.

User prompt (subsequent rounds)

Here is the transcript of the debate:

<transcript>
{transcript}
</transcript>

Now it's your turn to provide an argument.
