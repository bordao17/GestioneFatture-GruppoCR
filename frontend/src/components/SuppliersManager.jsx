import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, BrainCircuit, Info, Search, Plus } from 'lucide-react';

export default function SuppliersManager({ apiUrl, onBack }) {
  const [suppliers, setSuppliers] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);

  useEffect(() => {
    fetchSuppliers();
  }, []);

  const fetchSuppliers = async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/fornitori`);
      setSuppliers(res.data);
    } catch (err) {
      console.error("Errore nel caricamento fornitori:", err);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await axios.put(`${apiUrl}/api/fornitori`, suppliers);
      setSaveMessage({ type: 'success', text: 'Memoria AI aggiornata con successo!' });
      setTimeout(() => setSaveMessage(null), 3000);
    } catch (err) {
      setSaveMessage({ type: 'danger', text: 'Errore durante il salvataggio.' });
    } finally {
      setIsSaving(false);
    }
  };

  const updateSupplier = (name, field, value) => {
    setSuppliers(prev => ({
      ...prev,
      [name]: { ...prev[name], [field]: value }
    }));
  };

  const addNewSupplier = () => {
    const name = prompt("Inserisci la Ragione Sociale esatta del nuovo fornitore:");
    if (name && !suppliers[name]) {
      setSuppliers(prev => ({
        ...prev,
        [name]: { confermato: "no", note_specifiche: "" }
      }));
    }
  };

  const filteredSuppliers = Object.entries(suppliers).filter(([name]) => 
    name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="container-fluid px-4">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="fw-bold mb-0 d-flex align-items-center gap-2 text-info">
          <BrainCircuit size={28} /> Addestramento AI Fornitori
        </h4>
        <div className="d-flex gap-2">
          <button className="btn btn-outline-secondary px-4" onClick={onBack}>Torna alla Dashboard</button>
          <button className="btn btn-info px-4 fw-bold text-dark d-flex align-items-center gap-2 shadow-sm" onClick={handleSave} disabled={isSaving}>
            <Save size={18} /> {isSaving ? 'Salvataggio...' : 'Salva Memoria'}
          </button>
        </div>
      </div>

      {saveMessage && (
        <div className={`alert alert-${saveMessage.type} shadow-sm border-0 py-2`}>
          {saveMessage.text}
        </div>
      )}

      {/* BOX ISTRUZIONI AIUTO */}
      <div className="alert bg-info bg-opacity-10 border border-info border-opacity-25 text-light mb-4 shadow-sm">
        <h6 className="fw-bold text-info d-flex align-items-center gap-2 mb-3">
          <Info size={20} /> Come istruire correttamente l'Intelligenza Artificiale
        </h6>
        <p className="small mb-2">
          L'IA legge il documento come farebbe un umano. Quando scrivi le note specifiche per un fornitore critico, usa riferimenti <strong>spaziali</strong> (es. <em>in alto a destra</em>, <em>sotto la scritta X</em>) o regole di <strong>esclusione</strong> (es. <em>ignora la parola X</em>).
        </p>
        <div className="bg-dark p-3 rounded border border-secondary mt-3">
          <span className="badge bg-success mb-2">Esempio Eccellente</span>
          <code className="d-block text-light" style={{ fontSize: '0.85rem' }}>
            "IGNORA ASSOLUTAMENTE l'indirizzo 'VIA DEL RAME 06077 PONTE FELCINO PG'. Quella è la sede legale. 
            Il vero indirizzo di consegna si trova in alto a destra, esattamente sotto l'etichetta 'Luogo di destinazione'. 
            Estrai solo l'indirizzo scritto lì sotto."
          </code>
        </div>
      </div>

      <div className="card bg-dark border-secondary shadow-sm mb-5">
        <div className="card-header border-secondary d-flex justify-content-between align-items-center py-3">
          <div className="position-relative w-50">
            <Search className="position-absolute top-50 translate-middle-y text-secondary ms-3" size={18} />
            <input 
              type="text" 
              className="form-control bg-black text-light border-secondary ps-5 focus-ring" 
              placeholder="Cerca fornitore..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <button className="btn btn-outline-light btn-sm d-flex align-items-center gap-1" onClick={addNewSupplier}>
            <Plus size={16} /> Aggiungi Fornitore
          </button>
        </div>

        <div className="card-body p-0">
          <div className="list-group list-group-flush rounded-bottom">
            {filteredSuppliers.map(([name, data]) => (
              <div key={name} className="list-group-item bg-dark border-secondary p-4">
                <div className="row">
                  <div className="col-md-3 border-end border-secondary">
                    <h6 className="fw-bold text-light mb-3">{name}</h6>
                    
                    <div className="form-check form-switch mb-2">
                      <input 
                        className="form-check-input" 
                        type="checkbox" 
                        role="switch" 
                        id={`switch-${name}`}
                        checked={data.confermato === 'yes'}
                        onChange={(e) => updateSupplier(name, 'confermato', e.target.checked ? 'yes' : 'no')}
                      />
                      <label className="form-check-label small text-secondary" htmlFor={`switch-${name}`}>
                        Regola Attiva ({data.confermato})
                      </label>
                    </div>
                  </div>
                  
                  <div className="col-md-9 ps-md-4">
                    <label className="form-label small text-info fw-bold mb-1">Regola per il Modello AI (Prompt)</label>
                    <textarea 
                      className="form-control bg-black text-light border-secondary font-monospace" 
                      rows="3"
                      placeholder="Nessuna regola specifica per questo fornitore. Il modello userà la logica standard."
                      value={data.note_specifiche}
                      onChange={(e) => updateSupplier(name, 'note_specifiche', e.target.value)}
                      style={{ fontSize: '0.85rem' }}
                    />
                  </div>
                </div>
              </div>
            ))}
            
            {filteredSuppliers.length === 0 && (
              <div className="text-center py-5 text-secondary">
                Nessun fornitore trovato con questo nome.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}