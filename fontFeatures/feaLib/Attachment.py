# Code for converting a Attachment object into feaLib statements
import fontTools.feaLib.ast as feaast

def glyphref(g):
  if len(g) == 1:
    return feaast.GlyphName(g[0])
  return feaast.GlyphClass([feaast.GlyphName(x) for x in g])

def sortByAnchor(self):
  anchors = {}
  for name, pos in self.marks.items():
    if not pos in anchors:
      anchors[pos] = []
    anchors[pos].append(name)
  self.markslist =  [ (v, k) for k, v in anchors.items()]

  anchors = {}
  for name, pos in self.bases.items():
    if not pos in anchors:
      anchors[pos] = []
    anchors[pos].append(name)
  self.baseslist =  [ (v, k) for k, v in anchors.items() ]

def feaPreamble(self, ff):
  if self.is_cursive: return []
  sortByAnchor(self)
  if not "mark_classes_done" in ff.scratch:
    ff.scratch["mark_classes_done"] = {}
  b = feaast.Block()
  for mark in self.markslist:
    if not (self.base_name, tuple(mark[0])) in ff.scratch["mark_classes_done"]:
      b.statements.append(feaast.MarkClassDefinition(
        feaast.MarkClass(self.base_name),
        feaast.Anchor(*mark[1]),
        glyphref(mark[0])
      ))
      ff.scratch["mark_classes_done"][(self.base_name, tuple(mark[0]))] = True
  return [b]

def asFeaAST(self):
  b = feaast.Block()
  if self.is_cursive:
    allglyphs = set(self.bases.keys()) | set(self.marks.keys())
    for g in allglyphs:
      b.statements.append(feaast.CursivePosStatement(
        glyphref([g]),
        g in self.marks and feaast.Anchor(*self.marks[g]),
        g in self.bases and feaast.Anchor(*self.bases[g])
      ))
  else:
    if not hasattr(self, "baseslist"): sortByAnchor(self) # e.g. when testing
    for base in self.baseslist:
      b.statements.append(feaast.MarkBasePosStatement(
        glyphref(base[0]),
        [[
          feaast.Anchor(*base[1]),
          feaast.MarkClass(self.base_name)
        ]]
      ))

  return b
