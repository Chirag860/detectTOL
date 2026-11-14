# ruff: noqa
# Step 1 feasibility spike (docs/reports/phase-app-1.md). Not product code; needs SOLIDWORKS + pywin32.
import sys
from swlib import connect, typed, save_as
sw = connect(visible=True)
print("AP before:", sw.GetUserPreferenceIntegerValue(75), " PMI before:", sw.GetUserPreferenceToggle(704))
print("set AP242:", sw.SetUserPreferenceIntegerValue(75, int(sys.argv[3])), " set PMI:", sw.SetUserPreferenceToggle(704, True))
print("AP after:", sw.GetUserPreferenceIntegerValue(75), " PMI after:", sw.GetUserPreferenceToggle(704))
res = sw.OpenDoc6(sys.argv[1], 2, 1, "", 0, 0)
doc = typed(res[0] if isinstance(res, tuple) else res, "IModelDoc2")
save_as(doc, sys.argv[2])
print("exported", sys.argv[2])
