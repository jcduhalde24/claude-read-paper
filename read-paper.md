Convert an academic economics PDF to Markdown using MinerU Cloud API, then read it section by section. Preserves math/LaTeX, tables, and document structure. Uses fewer tokens than reading PDFs directly.

Usage: /read-paper <pdf_path_or_url>

Examples:
- `/read-paper Papers/angrist_krueger_1991.pdf`
- `/read-paper https://example.com/working_paper.pdf`

## Steps

1. Run `--quick` first to get a fast overview:
   ```bash
   python "$HOME/.claude/tools/pdf_to_md.py" "$ARGUMENTS" --quick --cache-dir "Papers/md_cache"
   ```
   This prints a structured summary: title, authors, JEL codes (if any), abstract, and section table with line counts.

2. **Read the introduction next** unless the user's question points to a specific section:
   - Asked about robustness/sensitivity → skip intro, read **appendix** directly
   - Asked about methodology/identification → skip intro, read **empirical strategy** section
   - Asked about results/findings → skip intro, read **results** section
   - General question / overview / no specific request → read **introduction** first
   ```bash
   python "$HOME/.claude/tools/pdf_to_md.py" "$ARGUMENTS" --section introduction --cache-dir "Papers/md_cache"
   ```
   Then read the file path that's printed.
   If `--section` returns an error ("no section matching"), run `--list` to see all available sections and retry with a corrected name. The script uses substring matching, so partial names work (e.g., "identif" matches "Identification and Estimation").

3. Based on what the user wants, read additional sections (see strategies below).

4. If `--quick` shows no abstract, garbled text, or missing sections, see error handling below.

## Flags
- `--quick`, `-q`: Print summary (title + abstract + TOC) to stdout — **use this first**
- `--section NAME`, `-s NAME`: Print path to section matching NAME (accent-insensitive substring match; prioritizes filename > header > content)
- `--full`: Print path to full paper.md (includes appendix and references — use `body.md` instead unless you need everything)
- `--list`: Print the full section index to stdout — **use when `--section` fails or sections look unusual**
- `--lang [en|es|pt|fr|de|it|zh|auto]`: OCR language (default: auto). Use `--lang es` for Spanish papers, etc. Works for both local files and URLs.
- `--no-cache`: Force re-conversion (also re-splits with latest version)
- `--cache-dir PATH`: Override cache directory (default: `~/.claude/tools/md_cache`; the commands above override it to `Papers/md_cache`)

## Error handling
- **API key missing**: Script prints "Error: MINERU_API_KEY not found". Tell the user to set `MINERU_API_KEY` env var or create `~/.claude/tools/mineru_config.json` with `{"api_key": "..."}`. Get a key at https://mineru.net.
- **Conversion fails / timeout**: Fall back to reading the PDF directly with the Read tool. Mention that OCR-heavy or scanned papers may need `--lang` flag.
- **Section not found**: Run `--list` to see available sections, then retry with a corrected name.
- **Empty/corrupted output**: Try `--no-cache --lang en` (or the appropriate language) to force re-conversion. If it persists, fall back to the Read tool on the original PDF.
- **Garbled text or missing sections in `--quick`**: Likely an OCR language mismatch. Rerun with `--no-cache --lang es` (or `pt`, `fr`, etc.) to force the correct language.
- **No abstract shown**: Common in NBER/CEPR working papers that lack an explicit abstract section. The introduction will contain the full argument — read it directly.

## Identify paper type first

Before reading in depth, check the abstract/introduction for paper type — the reading strategy differs:
- **Reduced-form causal inference** (most common): has identification section, results, robustness → follow standard strategies below
- **Structural estimation**: model section is central — look for parameters, moments, estimation method, counterfactuals
- **RCT / field experiment**: focus on experimental design, balance tables, ITT vs. LATE, compliance, attrition
- **Survey / literature review**: NO identification section — focus on taxonomy, key findings across studies, gaps, proposed agenda. Skip robustness.
- **Descriptive / correlational**: no causal claims — report what variation is used and what confounds remain

## Reading strategies for economics papers

### "What does this paper do?" / General overview
1. `--quick` gives you the abstract — that's the 30-second answer
2. Read the **introduction** for the full argument, contribution claims, and preview of results
3. That's usually enough. Only go deeper if asked.

### "How do they identify?" / Empirical strategy
1. Read the **empirical strategy / identification / methodology** section
2. Look for:
   - Estimating equation (report in LaTeX)
   - Identifying assumption (conditional independence, exclusion restriction, continuity at cutoff, parallel trends, etc.)
   - Source of exogenous variation (instrument, natural experiment, policy change, discontinuity)
   - Threats to identification and how they address them
   - Instrument validity / first stage (for IV papers)
   - Balance/covariate table: pre-treatment means by treatment status — check if covariates are balanced (small t-stats); imbalance suggests selection bias
3. Report: the equation, what varies, what's held fixed, fixed effects structure, level of clustering

### "What do they find?" / Results
1. Read the **results** section(s)
2. Report magnitudes relative to the mean (% effect), not just raw coefficients
3. Report the preferred specification first, then note if results hold across alternatives
4. Note economic significance vs. statistical significance — a precisely estimated zero is a finding too

### "Is it robust?" / Robustness
1. Read **appendix.md** — contains robustness checks, alternative specs, placebo tests
2. Key checks to look for:
   - Placebo/falsification tests (pre-trends, fake treatments, fake outcomes)
   - Alternative specifications (different FE, clustering, controls, functional form)
   - Sample restrictions (dropping outliers, subsamples, bandwidth sensitivity for RDD)
   - Alternative measures of key variables
   - Bounds (Lee bounds, Oster's delta, Conley et al. for exclusion restriction)
3. Read **references.md** only if the user asks about specific citations

### "What's the experiment?" / RCT design
1. Read the **experimental design / protocol** section
2. Report: randomization method, sample size, power calculations (if any), treatment/control definitions
3. Check **balance table** for covariate imbalances
4. In results, note:
   - ITT (intent-to-treat) vs. LATE (local average treatment effect)
   - Compliance rate (% treated in treatment arm, % untreated in control)
   - Attrition rate by arm and whether it's differential
   - Discussion of SUTVA / spillover concerns

### "What's the model?" / Theoretical framework
1. Read the **model / theory / framework** section
2. Look for: primitives (preferences, technology, constraints), equilibrium concept, key predictions
3. If structural: report the parameters being estimated and what moments identify them
4. Note whether the model is used for counterfactuals/welfare or just to motivate the empirical design

### "What mechanisms?" / Channels
1. Read the **mechanism / channels / heterogeneity** section(s)
2. Common approaches: heterogeneity by subgroup, mediation analysis, bounding exercises, model-implied tests
3. Report which channels are supported and which are ruled out

### "Read the whole paper"
1. Read **body.md** (intro through conclusion, without appendix or references)
2. Only read appendix if explicitly asked

### "Compare these papers"

For 2-3 papers:
1. Run `--quick` on each paper
2. Read introductions to understand each paper's claim and contribution
3. Read identification sections to compare approaches
4. Synthesize: what each does, how they differ in identification, whose estimates are more credible and why

For 4+ papers (token-efficient approach):
1. Run `--quick` on all papers first — compare abstracts side by side
2. Identify the 2-3 most relevant papers based on abstracts
3. Deep-read identification + results only for those
4. For the rest, summarize from abstract alone
5. Synthesize in a table: Paper | ID Strategy | Data | Main Result | Key Assumption

## Handling tables and figures
- **Tables are often images** — MinerU converts coefficient tables to `[image: ...]` placeholders. The numerical data is lost in those cases.
- **Workaround**: look for inline references in the prose text (e.g., "Table 3 shows beta = -0.05, SE = 0.02"). Most well-written economics papers state key numbers in the text.
- **If key numbers are only in table images**: report that the table data is not extractable from the markdown conversion. Provide the table number and a brief description of what it contains based on surrounding text. Suggest the user consult the original PDF for those specific tables.
- LaTeX equations and inline math ($...$, $$...$$) are preserved correctly.

## When reporting results from a paper
- Always report: point estimate, SE or CI, N, and significance level
- Compute effect size relative to the dependent variable mean when possible (% effect)
- State the identification strategy in one sentence (DiD, RDD, IV, RCT, structural, shift-share, bunching, synth control, etc.)
- Flag if standard errors are clustered and at what level
- Note sample restrictions that matter for external validity (country, time period, age group, industry, etc.)
- If there are multiple specifications, report the preferred one and note robustness
- For IV: report first-stage F-statistic and note weak instrument concerns if relevant
- For DiD: note whether they show pre-trends / event study evidence
- For RDD: note bandwidth, polynomial order, and whether results are sensitive to these
- For structural: note what moments identify the parameters and report model fit
- For bunching: report the bunching estimate (excess mass), bandwidth choice, and counterfactual distribution assumption
- For shift-share / Bartik: note whether they use Rotemberg weights or other diagnostics for share exogeneity
- For synthetic control: report pre-treatment fit (RMSPE), donor pool composition, and placebo inference

## File structure in project
```
Papers/md_cache/<paper_name>_<hash>/
  paper.md              — full document (avoid unless needed)
  sections/
    _index.md           — TOC with metadata (read first, or use --quick)
    00_abstract.md      — extracted abstract
    01_introduction.md, 02_data.md, ...  — main sections (subsections merged in)
    body.md             — main text (intro through conclusion, no appendix)
    appendix.md         — appendix + supplement
    references.md       — bibliography
```

Conversion is cached by file hash — repeat reads cost zero API calls (~190ms).
Old caches are automatically re-split with the latest splitting logic (no re-download needed).
If a paper has many sections (>12), subsections are auto-merged into their parent main section to keep the index manageable.
