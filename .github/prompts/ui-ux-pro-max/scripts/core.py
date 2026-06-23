#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, re
from pathlib import Path
from math import log
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
MAX_RESULTS = 3

CSV_CONFIG = {
    "style": {"file": "styles.csv", "search_cols": ["Style Category", "Keywords", "Best For", "Type", "AI Prompt Keywords"], "output_cols": ["Style Category", "Type", "Keywords", "Primary Colors", "Effects & Animation", "Best For", "Light Mode ✓", "Dark Mode ✓", "Performance", "Accessibility", "Framework Compatibility", "Complexity", "AI Prompt Keywords", "CSS/Technical Keywords", "Implementation Checklist", "Design System Variables"]},
    "color": {"file": "colors.csv", "search_cols": ["Product Type", "Notes"], "output_cols": ["Product Type", "Primary", "On Primary", "Secondary", "On Secondary", "Accent", "On Accent", "Background", "Foreground", "Card", "Card Foreground", "Muted", "Muted Foreground", "Border", "Destructive", "On Destructive", "Ring", "Notes"]},
    "chart": {"file": "charts.csv", "search_cols": ["Data Type", "Keywords", "Best Chart Type", "When to Use", "When NOT to Use", "Accessibility Notes"], "output_cols": ["Data Type", "Keywords", "Best Chart Type", "Secondary Options", "When to Use", "When NOT to Use", "Data Volume Threshold", "Color Guidance", "Accessibility Grade", "Accessibility Notes", "A11y Fallback", "Library Recommendation", "Interactive Level"]},
    "landing": {"file": "landing.csv", "search_cols": ["Pattern Name", "Keywords", "Conversion Optimization", "Section Order"], "output_cols": ["Pattern Name", "Keywords", "Section Order", "Primary CTA Placement", "Color Strategy", "Conversion Optimization"]},
    "product": {"file": "products.csv", "search_cols": ["Product Type", "Keywords", "Primary Style Recommendation", "Key Considerations"], "output_cols": ["Product Type", "Keywords", "Primary Style Recommendation", "Secondary Styles", "Landing Page Pattern", "Dashboard Style (if applicable)", "Color Palette Focus"]},
    "ux": {"file": "ux-guidelines.csv", "search_cols": ["Category", "Issue", "Description", "Platform"], "output_cols": ["Category", "Issue", "Platform", "Description", "Do", "Don't", "Code Example Good", "Code Example Bad", "Severity"]},
    "typography": {"file": "typography.csv", "search_cols": ["Font Pairing Name", "Category", "Mood/Style Keywords", "Best For", "Heading Font", "Body Font"], "output_cols": ["Font Pairing Name", "Category", "Heading Font", "Body Font", "Mood/Style Keywords", "Best For", "Google Fonts URL", "CSS Import", "Tailwind Config", "Notes"]},
    "icons": {"file": "icons.csv", "search_cols": ["Category", "Icon Name", "Keywords", "Best For"], "output_cols": ["Category", "Icon Name", "Keywords", "Library", "Import Code", "Usage", "Best For", "Style"]},
    "react": {"file": "react-performance.csv", "search_cols": ["Category", "Issue", "Keywords", "Description"], "output_cols": ["Category", "Issue", "Platform", "Description", "Do", "Don't", "Code Example Good", "Code Example Bad", "Severity"]},
    "web": {"file": "app-interface.csv", "search_cols": ["Category", "Issue", "Keywords", "Description"], "output_cols": ["Category", "Issue", "Platform", "Description", "Do", "Don't", "Code Example Good", "Code Example Bad", "Severity"]},
    "google-fonts": {"file": "google-fonts.csv", "search_cols": ["Family", "Category", "Stroke", "Classifications", "Keywords", "Subsets", "Designers"], "output_cols": ["Family", "Category", "Stroke", "Classifications", "Styles", "Variable Axes", "Subsets", "Designers", "Popularity Rank", "Google Fonts URL"]},
    "prompt": {"file": "styles.csv", "search_cols": ["Style Category", "AI Prompt Keywords", "CSS/Technical Keywords"], "output_cols": ["Style Category", "AI Prompt Keywords", "CSS/Technical Keywords"]},
}

STACK_CONFIG = {s: {"file": f"stacks/{s}.csv"} for s in ["react","nextjs","vue","svelte","astro","swiftui","react-native","flutter","nuxtjs","nuxt-ui","html-tailwind","shadcn","jetpack-compose","threejs","angular","laravel","javafx"]}
_STACK_COLS = {"search_cols": ["Category", "Guideline", "Description", "Do", "Don't"], "output_cols": ["Category", "Guideline", "Description", "Do", "Don't", "Code Good", "Code Bad", "Severity", "Docs URL"]}
AVAILABLE_STACKS = list(STACK_CONFIG.keys())

class BM25:
    def __init__(self, k1=1.5, b=0.75): self.k1=k1; self.b=b; self.corpus=[]; self.doc_lengths=[]; self.avgdl=0; self.idf={}; self.doc_freqs=defaultdict(int); self.N=0
    def tokenize(self, text): text=re.sub(r'[^\w\s]', ' ', str(text).lower()); return [w for w in text.split() if len(w)>=2]
    def fit(self, documents):
        self.corpus=[self.tokenize(d) for d in documents]; self.N=len(self.corpus)
        if not self.N: return
        self.doc_lengths=[len(d) for d in self.corpus]; self.avgdl=sum(self.doc_lengths)/self.N
        for doc in self.corpus:
            seen=set()
            for w in doc:
                if w not in seen: self.doc_freqs[w]+=1; seen.add(w)
        for w,f in self.doc_freqs.items(): self.idf[w]=log((self.N-f+0.5)/(f+0.5)+1)
    def score(self, query):
        qt=self.tokenize(query); scores=[]
        for idx,doc in enumerate(self.corpus):
            s=0; dl=self.doc_lengths[idx]; tf=defaultdict(int)
            for w in doc: tf[w]+=1
            for t in qt:
                if t in self.idf: f=tf[t]; s+=self.idf[t]*f*(self.k1+1)/(f+self.k1*(1-self.b+self.b*dl/self.avgdl))
            scores.append((idx,s))
        return sorted(scores, key=lambda x: x[1], reverse=True)

def _load_csv(fp):
    with open(fp,'r',encoding='utf-8') as f: return list(csv.DictReader(f))

def _search_csv(fp, sc, oc, query, n):
    if not fp.exists(): return []
    data=_load_csv(fp); docs=[" ".join(str(r.get(c,"")) for c in sc) for r in data]
    bm25=BM25(); bm25.fit(docs); ranked=bm25.score(query)
    return [{c: r.get(c,"") for c in oc if c in r} for idx,score in ranked[:n] if score>0 for r in [data[idx]]]

def detect_domain(query):
    q=query.lower()
    kws={"color":["color","palette","hex","rgb","token","semantic","accent","destructive","muted"],"chart":["chart","graph","visualization","trend","bar","pie","scatter"],"landing":["landing","page","cta","conversion","hero","testimonial"],"product":["saas","ecommerce","fintech","healthcare","travel","dashboard","booking"],"style":["style","design","ui","minimalism","glassmorphism","dark mode","flat"],"ux":["ux","usability","accessibility","touch","animation","navigation","mobile"],"typography":["font pairing","typography pairing","heading font","body font"],"google-fonts":["google font","font family","font"],"icons":["icon","lucide","heroicons"],"react":["react","next.js","suspense","memo","rerender","bundle"],"web":["aria","focus","semantic","form","input"]}
    scores={d:sum(1 for kw in words if re.search(r'\b'+re.escape(kw)+r'\b',q)) for d,words in kws.items()}
    best=max(scores, key=scores.get); return best if scores[best]>0 else "style"

def search(query, domain=None, max_results=MAX_RESULTS):
    if domain is None: domain=detect_domain(query)
    config=CSV_CONFIG.get(domain, CSV_CONFIG["style"])
    fp=DATA_DIR/config["file"]
    if not fp.exists(): return {"error": f"File not found: {fp}", "domain": domain}
    results=_search_csv(fp, config["search_cols"], config["output_cols"], query, max_results)
    return {"domain": domain, "query": query, "file": config["file"], "count": len(results), "results": results}

def search_stack(query, stack, max_results=MAX_RESULTS):
    if stack not in STACK_CONFIG: return {"error": f"Unknown stack: {stack}"}
    fp=DATA_DIR/STACK_CONFIG[stack]["file"]
    if not fp.exists(): return {"error": f"Stack file not found: {fp}", "stack": stack}
    results=_search_csv(fp, _STACK_COLS["search_cols"], _STACK_COLS["output_cols"], query, max_results)
    return {"domain": "stack", "stack": stack, "query": query, "file": STACK_CONFIG[stack]["file"], "count": len(results), "results": results}
