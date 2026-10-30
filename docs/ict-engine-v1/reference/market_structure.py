from dataclasses import dataclass
@dataclass(frozen=True)
class Pivot:
    index: int
    known_at: int
    kind: str
    price: float
def confirmed_pivots(bars,left,right):
    out=[]
    for i in range(left,len(bars)-right):
        others=bars[i-left:i]+bars[i+1:i+right+1]
        if all(bars[i].h>x.h for x in others): out.append(Pivot(i,i+right,'HIGH',bars[i].h))
        if all(bars[i].l<x.l for x in others): out.append(Pivot(i,i+right,'LOW',bars[i].l))
    return out
