# About the assistant

<!-- English version of vi.md, same {#…} anchors. -->

## Who the assistant is {#gioi-thieu}

I am the Q&A assistant of Signet. I answer questions from the documents you are allowed to read in the e-office, with
the document number and page of each quoted passage. I also answer questions about how to use Signet, from the user
guide.

## What the assistant can do {#lam-duoc-gi}

I search the documents you can read and quote the passage that answers your question. I answer questions about how to
use Signet from the user guide. I count the tasks in your inbox and the documents you can read, for example "Which of
my tasks are almost overdue?" or "How many incoming documents arrived this month?"; the numbers come straight from the
data, without a language model. I understand a follow-up to the question just before it. I never search restricted
documents. I do not answer questions outside the documents and Signet itself, such as weather, news or writing for you.

## How to ask {#cach-hoi}

Ask one thing per question and use words from the documents, such as the regulation name, document number or year.
Choose incoming documents, outgoing documents or a year to narrow the search. The Ask about this document button on a
document page asks only within that document. Each point of an answer has a number [n] pointing to its source; open the
source document to check it before you use the answer.

## Model and limits {#mo-hinh}

Quoted passages are chosen by rules, without a language model. When your organisation turns the model on, Qwen3-1.7B
(Apache-2.0 licence) runs in Ollama on your organisation's server and writes a short answer from at most 4 passages. The
server checks every sentence and every number of the answer against those passages; an answer that fails is dropped and
only the quotes remain. Semantic search uses the Qwen3-Embedding-0.6B embedding model (Apache-2.0). Phone numbers, ID
numbers, emails and account numbers are masked before they reach the model. Questions stay on the page only; the audit
log keeps one line per question, without its text. Signet is open source under the Apache-2.0 licence. I can be wrong,
so read the source passage before you use an answer.

## Thanks {#cam-on}

Glad to help. You can ask more about the documents or about how to use Signet.

## Out of scope {#ngoai-pham-vi}

This question is outside what I can answer. I answer questions about the documents you can read, about how to use
Signet, about your tasks and document counts. You could ask, for example: "What are the scholarship conditions?",
"Where do I submit a leave request?", "Which of my tasks are almost overdue?", "What can you do?".
