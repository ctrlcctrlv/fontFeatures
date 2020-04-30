import re
from fontFeatures import FontFeatures, Routine, Substitution, Chaining
from fontFeatures.optimizer import Optimizer
from fontTools.ttLib import TTFont

class FontDameUnparser():
  def __init__(self, lines, config = {}, glyphset = ()):
    self.all_languages = []
    self.lines = lines
    self.script_applications = {}
    self.features = {}
    self.lookups = {}
    self.dependencies = {}
    self.classes = []
    self.config = config
    self.glyphset = glyphset
    self.current_lookup = None
    self.state = "doing_nothing"
    self.ff = FontFeatures()
    self.resetContexts()

  def resetContexts(self):
    self.classContexts = {}
    self.backtrackclassContexts = {}
    self.lookaheadclassContexts = {}

  def unparse(self):
    # Parse lookups
    for line in self.lines:
      self.parse_line(line)

    # Tidy up lookups
    for lid, lu in self.lookups.items():
      for rule in lu.rules:
        if not isinstance(rule, Chaining): continue
        pretendlookups = rule.lookups
        reallookups = [ None ] * len(rule.input)
        for i in pretendlookups:
          m = re.match("(\\d+),\\s*(\\d+)", i)
          if not lid in self.dependencies: self.dependencies[lid] = []
          self.dependencies[lid].append(m[2])
          if not reallookups[int(m[1])-1]:
            reallookups[int(m[1])-1] = []
          reallookups[int(m[1])-1].append( self.lookups[m[2]] )
        rule.lookups = reallookups

    # Rearrange into features
    self.base_lu_for_feature = {}
    self.toplevel_lookups = set()
    for i in sorted(self.features.keys()):
      feat = self.features[i]
      tag = feat["tag"]
      if "DFLT/default" in feat["languages_and_scripts"]:
        self.base_lu_for_feature[tag] = set(feat["lookups"])
        lookups = [self.lookups[x] for x in feat["lookups"]]
      else:
        # Set difference
        feat["lookups"] = [item for item in feat["lookups"] if item not in self.base_lu_for_feature[tag]]
        lookups = [self.lookups[x] for x in feat["lookups"]]
        langcode = [ tuple(x.split("/")) for x in feat["languages_and_scripts"] ]
        # Clone the routines just in case
        lookups = [
          Routine(languages=langcode, rules=lu.rules) for lu in lookups
        ]

      self.ff.addFeature(tag, lookups)
      for lu in feat["lookups"]:
        self.toplevel_lookups.add(lu)

    # Delete toplevel lookups from lookup table
    for l in self.toplevel_lookups:
      del self.lookups[l]

    # Rearrange lookups into dependency order
    done = {}
    def dolookup(lid):
      if lid in done: return
      if lid in self.dependencies:
        for x in self.dependencies[lid]:
          dolookup(x)
      self.ff.routines.append(self.lookups[lid])
      done[lid] = True

    for i in self.lookups.keys():
      dolookup(i)

  def parse_line(self, line):
    if line == "\n": return
    elif line == "script table begin\n":
      self.state = "reading_script_table"
      return
    elif line == "feature table begin\n":
      self.state = "reading_feature_table"
      return
    elif line == "class definition begin\n":
      self.state = "reading_class_definition"
      return
    elif line == "backtrackclass definition begin\n":
      self.state = "reading_backtrackclass_definition"
      return
    elif line == "lookaheadclass definition begin\n":
      self.state = "reading_lookaheadclass_definition"
      return

    elif line == "class definition end\n":
      self.state = "parsing_lookup"
      return
    elif line == "feature table end\n":
      self.end_feature_table()
      self.state = "doing_nothing"
      return
    elif line == "lookup end\n":
      self.end_lookup()
      self.state = "doing_nothing"
      return
    elif line == "script table end\n":
      self.state = "doing_nothing"
      return
    elif line.startswith("lookup"):
      self.parse_lookup_header(line)
      self.state = "parsing_lookup"
      return

    if self.state == "reading_script_table":
      self.add_to_script_table(line)
    elif self.state == "reading_feature_table":
      self.add_to_feature_table(line)
    elif self.state == "parsing_lookup":
      self.add_to_lookup(line)
    elif self.state == "reading_class_definition":
      self.add_to_class_definition("class", line)
    elif self.state == "reading_backtrackclass_definition":
      self.add_to_class_definition("backtrackclass", line)
    elif self.state == "reading_lookaheadclass_definition":
      self.add_to_class_definition("lookaheadclass", line)



  def add_to_script_table(self, line):
    m = re.match("^(\\w+)\\s+(\\w+)\\s+(.*)$", line)
    lang = m[1]+"/"+m[2]
    self.all_languages.append(lang)
    for f in m[3].split(", "):
      f = int(f)
      if not (f in self.script_applications):
        self.script_applications[f] = []
      self.script_applications[f].append( lang )

  def add_to_feature_table(self, line):
    m = re.match("^(\w+)\s+(\w+)\s+(.*)$", line)
    self.features[int(m[1])] = {
      "tag": m[2],
      "lookups": m[3].split(", "),
      "languages_and_scripts": self.script_applications[int(m[1])]
    }

  def end_feature_table(self):
    pass

  def end_lookup(self):
    # print("Parsed lookup %s" % self.current_lookup.name)
    # Optimizer().optimize_routine(self.current_lookup)
    self.current_lookup = None
    self.resetContexts()

  def parse_lookup_header(self, line):
    m = re.match("^lookup\s+(\w+)\s+(.*)$", line)
    self.current_lookup = Routine(name="lookup_%s"%m[1])
    self.lookups[m[1]] = self.current_lookup
    self.current_lookup_type = m[2]

  def get_class(self, cid, lookup):
    res = lookup["classes"][cid]
    if len(res) == 1: return res[0]
    if len(res) > 5:
      if not tuple(res) in self.classes:
        self.classes.append(tuple(res))
      classname = "@class%i" % self.classes.index(tuple(res))
      if classname in self.config: return self.config[classname]
      return classname

    return res

  def append_lookup_flag(self, flag):
    # XXX
    pass

  def add_subst(self, in_, out_):
    self.current_lookup.addRule(Substitution(in_,out_))

  def add_chain_simple(self, context, lookups):
    # XXX Lookups
    # print("Simple chaining %s, lookups = %s" % (self.current_lookup.name,lookups))
    self.current_lookup.addRule(Chaining(context,lookups=lookups))

  def add_to_lookup(self, line):
    m = re.match("(\w+)\s+(yes|no)", line)
    if m:
      if m[2] == "yes":
        self.append_lookup_flag(m[1])
      return
    m = re.match("MarkAttachmentType\s+(\d+)", line)
    if m:
      self.append_lookup_flag(m[1]) # XXX
      return

    if self.current_lookup_type == "single":
      m = re.match("([\w\.]+)\s+([\w\.]+)\n", line)
      self.add_subst([[m[1]]], [[m[2]]])

    elif self.current_lookup_type == "multiple":
      m = re.match("([\w\.]+)\s+(.*)\n", line)
      self.add_subst([[m[1]]], [ [x] for x in m[2].split("\t")])

    elif self.current_lookup_type == "ligature":
      m = re.match("([\w\.]+)\s(.*)\n", line)
      self.add_subst([[m[2]]],[m[1].split("\t")])

    elif self.current_lookup_type == "context":
      if line.startswith("glyph"):
        m = line.rstrip().split("\t")
        context = [ [x] for x in m[1].split(", ") ]
        self.add_chain_simple(context, m[2:])
      elif line.startswith("class"):
        m = line.rstrip().split("\t")
        context = self.make_context(m[1].split(", "), self.classContexts)
        self.add_chain_simple(context, m[2:])
    elif self.current_lookup_type == "chained":
      if line.startswith("class-chain"):
        m = re.match("class-chain\t([^\t]*)\t([^\t]*)\t([^\t]*)\t(.*)$", line)
        precontext = []
        if m[1]: precontext = self.make_context(m[1].split(", "), self.backtrackclassContexts)
        context = self.make_context(m[2].split(", "), self.classContexts)
        postcontext = []
        if m[3]:
          postcontext = self.make_context(m[3].split(", "), self.lookaheadclassContexts)
        lookups = m[4].rstrip().split("\t")
        # print("Lookup %s, lookups = %s" % (self.current_lookup.name, lookups))
        self.current_lookup.addRule(Chaining(context,
          precontext = precontext,
          postcontext = postcontext,
          lookups=lookups))
      else:
        print(line)
        raise ValueError("Unsupported lookup type %s" % self.current_lookup_type)

      pass

  def make_context(self, classlist, which):
    context = []
    for x in classlist:
      if x == "0":
        if not self.glyphset:
          raise ValueError("Class 0 in contextual but I don't know the glyphset")
        else:
          # Class 0 is everything that's not mentioned elsewhere
          members = set(self.glyphset)
          for c in which.values():
            members = members - set(c)
      else:
        members = which[x]
      context.append(members)
    return context

  def add_to_class_definition(self, which, line):
    m = re.match("([\w\.]+)\s+(\d+)", line)
    if which == "class":
      which = self.classContexts
    elif which == "backtrackclass":
      which = self.backtrackclassContexts
    elif which == "lookaheadclass":
      which = self.lookaheadclassContexts

    if not m[2] in which: which[m[2]] = []
    which[m[2]].append(m[1])

def apply_transformations(rule,parsed):
  context = list(rule["context"])
  transformations = {}
  for pos,lid in [ t.split(", ") for t in rule["transformations"] ]:
    transformations[int(pos)-1] = self.lookups[lid]

  for ix,c in reversed(list(enumerate(context))):
    if ix in transformations:
      # We have a transformation for this context
      lookup = transformations[ix]
      if self.current_lookup_type == "single"  and isinstance(context[ix],str) and not(context[ix].startswith("@")):
        for r in lookup["rules"]:
          if context[ix] == r[0]: context[ix] = r[1]
      elif self.current_lookup_type == "multiple" and isinstance(context[ix],str)  and not(context[ix].startswith("@")):
        for r in lookup["rules"]:
          if context[ix] == r[0]:
            if ix < len(context):
              context = context[:ix] + r[1] + context[ix+1:]
            else:
              context = context[:ix] + r[1]
      else:
        lookupname = "Lookup" + str(lid)
        if lookupname in self.config: lookupname = self.config[lookupname]
        context[ix] = "%s($%i)" % (lookupname,ix+1)

    else:
      context[ix] = "$%i" % (ix+1)
    if isinstance(context[ix], list):
      context[ix] = "[%s]" % ' '.join(context[ix])
  return context

def unparse(filename, config={}, font=None):
  if config:
    import json
    with open(config) as f:
        config = json.load(f)
  else:
    config = {}
  if font:
    glyphset = TTFont(font).getGlyphSet().keys()
  else:
    glyphset = ()
  with open(filename) as file_in:
    parser = FontDameUnparser(file_in,config, glyphset)
    parser.unparse()
  output = ""
  done = {}

  return parser.ff