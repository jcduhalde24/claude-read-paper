# /read-paper

A [Claude Code](https://claude.ai/code) skill that converts economics PDFs to Markdown using the [MinerU](https://mineru.net) Cloud API, then reads them section by section. Preserves math/LaTeX, tables, and document structure while using fewer tokens than reading PDFs directly.

Built for economics research: understands paper structure (identification, results, robustness), extracts JEL codes, and has reading strategies for DiD, IV, RDD, RCT, structural estimation, bunching, shift-share, and synthetic control.

Includes a **summarize-paper agent** that reads a full paper and produces a structured summary for literature reviews.

## Requirements

- [Claude Code](https://claude.ai/code)
- Python 3.9+
- A free MinerU API key from [mineru.net](https://mineru.net)

## Installation

```bash
git clone https://github.com/jcduhalde24/claude-read-paper.git
cd claude-read-paper
bash install.sh
```

The installer will:
1. Copy the skill, script, and agent to `~/.claude/`
2. Install Python dependencies (`requests`)
3. Prompt you for your MinerU API key

### Manual installation

If you prefer to install manually:

```bash
# Copy files
cp pdf_to_md.py ~/.claude/tools/
cp read-paper.md ~/.claude/commands/
cp summarize-paper.md ~/.claude/agents/

# Install dependencies
pip install requests

# Configure API key (pick one)
export MINERU_API_KEY="your-key-here"
# OR
echo '{"api_key": "your-key-here"}' > ~/.claude/tools/mineru_config.json
```

## Usage

### /read-paper skill

Read a paper interactively in Claude Code:

```
/read-paper path/to/paper.pdf
/read-paper https://example.com/working_paper.pdf
```

Ask questions like:
- "What does this paper do?" -- reads abstract + introduction
- "How do they identify?" -- reads empirical strategy section
- "Is it robust?" -- reads appendix with robustness checks
- "Compare these two papers" -- reads key sections from both and synthesizes

### summarize-paper agent

Ask Claude to use the agent on any paper for a structured lit review summary:

```
Use the summarize-paper agent on Papers/angrist_krueger_1991.pdf
```

The agent will:
1. Read the paper section by section (introduction, identification, results, mechanisms, robustness)
2. Produce a structured summary with: research question, data, identification strategy, main findings (with magnitudes), mechanisms, robustness, limitations, and key takeaway
3. Save it to `Papers/summaries/<author_year>.md`

### Language support

The default OCR language is auto-detected. For non-English papers, specify:

```
/read-paper paper_in_spanish.pdf
```

Then tell Claude to use `--lang es` (or `pt`, `fr`, `de`, `it`, `zh`).

## Updating

```bash
cd claude-read-paper
git pull
bash install.sh
```

The installer detects existing files and asks before overwriting.

## Uninstall

```bash
rm ~/.claude/tools/pdf_to_md.py
rm ~/.claude/commands/read-paper.md
rm ~/.claude/agents/summarize-paper.md
rm ~/.claude/tools/mineru_config.json  # optional: keeps your API key
```

## How it works

```
PDF  -->  MinerU Cloud API  -->  Markdown  -->  Split into sections  -->  Claude reads on demand
                                    |
                              Cached by file hash
                              (repeat reads: ~190ms)
```

Cache structure:
```
Papers/md_cache/<paper_name>_<hash>/
  paper.md              -- full document
  sections/
    _index.md           -- TOC with metadata
    00_abstract.md
    01_introduction.md
    02_data.md
    ...
    body.md             -- intro through conclusion
    appendix.md         -- appendix + supplement
    references.md       -- bibliography
```
