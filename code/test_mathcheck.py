import sys; import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mathcheck import *
def fake(code): return lambda msgs: "```python\n" + code + "\n```"
def M(q, opts, ans): return {"question": q, "options": opts, "answer": ans, "explanation": ""}
cases = [
 # (name, mcq, model's program, expected status)
 ("radar range wrong key (real failure #17)",
  M("A radar has PRF 10 kHz. What is the maximum unambiguous range?", ["1.5 km","15 km","150 km","1500 km"], "C"),
  "c=3e8\nprf=10e3\nanswer=c/(2*prf)/1000", "wrong_key"),
 ("radar range correct",
  M("A radar has PRF 10 kHz. What is the maximum unambiguous range?", ["1.5 km","15 km","150 km","1500 km"], "B"),
  "c=3e8\nprf=10e3\nanswer=c/(2*prf)/1000", "verified"),
 ("atan no option (real failure)",
  M("Find the angle of 30+j40.", ["36.9°","45°","60°","30°"], "A"),
  "import math\nanswer=math.degrees(math.atan2(40,30))", "no_match"),
 ("Wheatstone 240 no option (real failure)",
  M("In a balanced bridge P=100, Q=80, R=300. Find S.", ["150 Ω","200 Ω","300 Ω","375 Ω"], "D"),
  "P,Q,R=100,80,300\nanswer=Q*R/P", "no_match"),
 ("percent as fraction",
  M("Precision with TP=180, FP=120?", ["40%","50%","60%","70%"], "C"),
  "answer=180/(180+120)", "verified"),
 ("bit pattern (Cohen-Sutherland, real failure #12)",
  M("What is 0100 AND 0001?", ["0000","0001","0100","0101"], "B"),
  "answer=format(0b0100 & 0b0001,'04b')", "wrong_key"),
 ("conceptual question skipped",
  M("Which condition is not needed for deadlock?", ["Mutual exclusion","Hold and wait","Preemption","Circular wait"], "C"),
  "answer=None", "not_math"),
 ("model says no calc",
  M("Which cluster size N is valid?", ["1","2","5","7"], "D"), "answer=None", "not_math"),
 ("os import blocked",
  M("x?", ["1","2","3","4"], "A"), "import os\nanswer=1", "unchecked"),
 ("open blocked",
  M("x?", ["1","2","3","4"], "A"), "open('a','w')\nanswer=1", "unchecked"),
 ("dunder escape blocked",
  M("x?", ["1","2","3","4"], "A"), "answer=().__class__.__bases__", "unchecked"),
 ("infinite loop killed",
  M("x?", ["1","2","3","4"], "A"), "for i in iter(int,1): pass\nanswer=1", "unchecked"),
 ("memory bomb killed",
  M("x?", ["1","2","3","4"], "A"), "a=[0]*(10**10)\nanswer=1", "unchecked"),
 ("crash handled",
  M("x?", ["1","2","3","4"], "A"), "answer=1/0", "unchecked"),
 ("sqrt(12) frequency reuse (real failure #15)",
  M("D/R for N=4 cells?", ["1.73","2.45","3.46","4.00"], "A"), "import math\nanswer=math.sqrt(3*4)", "wrong_key"),
]
ok = 0
for name, mcq, code, want in cases:
    r = math_check(mcq, fake(code))
    good = r["status"] == want; ok += good
    print("PASS" if good else "FAIL", "|", name, "|", r["status"], "|", r.get("value", r.get("errors", ""))) 
print(f"{ok}/{len(cases)} passed")
