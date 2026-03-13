import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

function CustomSelect({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = options.find(o => String(o.value) === String(value));

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="csel" ref={ref}>
      <button className="csel-trigger" onClick={() => setOpen(!open)} type="button">
        <span>{selected ? selected.label : placeholder || "Select..."}</span>
        <ChevronDown size={13} className={open ? "csel-chev open" : "csel-chev"} />
      </button>
      {open && (
        <div className="csel-menu">
          {options.map(o => (
            <div key={o.value} className={`csel-opt ${String(o.value) === String(value) ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); }}>
              {o.logo && <img src={o.logo} alt="" style={{ width: 18, height: 18, borderRadius: 3 }} />}
              {o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CustomSelect;
