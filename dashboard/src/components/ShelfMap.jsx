import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Grip, Plus, Trash2, X } from 'lucide-react';

const CANVAS_HEIGHT = 520;

const HEALTH_STYLES = {
  green: {
    background: '#EAF3DE',
    border: '#3B6D11',
    text: '#27500A',
  },
  amber: {
    background: '#FAEEDA',
    border: '#854F0B',
    text: '#633806',
  },
  red: {
    background: '#FCEBEB',
    border: '#A32D2D',
    text: '#A32D2D',
  },
};

function normalizeSection(section) {
  return {
    id: section.id,
    name: section.name,
    x: section.x,
    y: section.y,
    width: section.width,
    height: section.height,
    products: (section.products || []).map((product) => ({
      product_id: product.product_id,
      name: product.product_name || product.name,
      current_stock: product.current_stock ?? 0,
    })),
  };
}

function getHealthStyle(section) {
  const products = section.products || [];
  if (!products.length) return HEALTH_STYLES.green;
  const average = products.reduce((sum, product) => sum + (product.current_stock || 0), 0) / products.length;
  if (average > 12) return HEALTH_STYLES.green;
  if (average >= 5) return HEALTH_STYLES.amber;
  return HEALTH_STYLES.red;
}

function clampSection(section) {
  return {
    ...section,
    x: Math.max(0, section.x),
    y: Math.max(0, section.y),
    width: Math.max(80, section.width),
    height: Math.max(60, section.height),
  };
}

export default function ShelfMap({ refetch = 0 }) {
  const canvasRef = useRef(null);
  const dragStateRef = useRef(null);
  const [sections, setSections] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [hoveredId, setHoveredId] = useState(null);
  const [activeModal, setActiveModal] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchSections = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/shelf-map');
      const data = await response.json();
      if (Array.isArray(data)) {
        setSections(data.map(normalizeSection));
      } else {
        console.warn('Expected array for shelf map sections, got:', data);
        setSections([]);
      }
    } catch (error) {
      console.error('Failed to fetch shelf map:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchInventory = async () => {
    try {
      const response = await fetch('/api/inventory');
      const data = await response.json();
      if (Array.isArray(data)) {
        setInventory(data);
      } else {
        console.warn('Expected array for inventory options, got:', data);
        setInventory([]);
      }
    } catch (error) {
      console.error('Failed to fetch inventory options:', error);
    }
  };

  useEffect(() => {
    fetchSections();
    fetchInventory();
  }, []);

  useEffect(() => {
    if (!refetch) return;
    fetchSections();
  }, [refetch]);

  const persistSection = async (section) => {
    await fetch(`/api/shelf-map/section/${section.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: section.name,
        x: section.x,
        y: section.y,
        width: section.width,
        height: section.height,
        product_ids: section.products.map((product) => product.product_id),
      }),
    });
  };

  const beginPointerInteraction = (event, section, mode) => {
    event.preventDefault();
    event.stopPropagation();
    dragStateRef.current = {
      mode,
      sectionId: section.id,
      startX: event.clientX,
      startY: event.clientY,
      originX: section.x,
      originY: section.y,
      originWidth: section.width,
      originHeight: section.height,
      moved: false,
    };
  };

  const handleCanvasMouseMove = (event) => {
    if (!dragStateRef.current) return;

    const { sectionId, mode, startX, startY, originX, originY, originWidth, originHeight } = dragStateRef.current;
    const deltaX = event.clientX - startX;
    const deltaY = event.clientY - startY;

    dragStateRef.current.moved = true;

    setSections((prev) => prev.map((section) => {
      if (section.id !== sectionId) return section;
      if (mode === 'drag') {
        return clampSection({ ...section, x: originX + deltaX, y: originY + deltaY });
      }
      return clampSection({ ...section, width: originWidth + deltaX, height: originHeight + deltaY });
    }));
  };

  const handleCanvasMouseUp = async () => {
    if (!dragStateRef.current) return;
    const { sectionId, moved } = dragStateRef.current;
    dragStateRef.current = null;
    if (!moved) return;
    const updated = sections.find((section) => section.id === sectionId);
    if (!updated) return;
    try {
      await persistSection(updated);
      await fetchSections();
    } catch (error) {
      console.error('Failed to persist shelf section position:', error);
    }
  };

  const closeModal = () => setActiveModal(null);

  const openModal = (section) => {
    if (dragStateRef.current?.moved) return;
    setActiveModal({
      id: section.id,
      name: section.name,
      x: section.x,
      y: section.y,
      width: section.width,
      height: section.height,
      products: section.products.map((product) => ({ ...product })),
    });
  };

  const availableProducts = useMemo(
    () => inventory.map((item) => ({
      product_id: item.id,
      name: item.product_name,
      current_stock: item.current_stock ?? 0,
    })),
    [inventory]
  );

  const addSection = async (size) => {
    try {
      const response = await fetch('/api/shelf-map/section', { method: 'POST' });
      const created = normalizeSection(await response.json());
      const next = {
        ...created,
        width: size.width,
        height: size.height,
      };
      setSections((prev) => [...prev, next]);
      await persistSection(next);
      await fetchSections();
    } catch (error) {
      console.error('Failed to create shelf section:', error);
    }
  };

  const saveModal = async () => {
    if (!activeModal) return;
    try {
      await fetch(`/api/shelf-map/section/${activeModal.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: activeModal.name,
          x: activeModal.x,
          y: activeModal.y,
          width: activeModal.width,
          height: activeModal.height,
          product_ids: activeModal.products.map((product) => product.product_id),
        }),
      });
      closeModal();
      await fetchSections();
    } catch (error) {
      console.error('Failed to save shelf section:', error);
    }
  };

  const deleteSection = async () => {
    if (!activeModal) return;
    try {
      await fetch(`/api/shelf-map/section/${activeModal.id}`, {
        method: 'DELETE',
      });
      setSections((prev) => prev.filter((section) => section.id !== activeModal.id));
      closeModal();
    } catch (error) {
      console.error('Failed to delete shelf section:', error);
    }
  };

  const updateModalProduct = (index, productId) => {
    const matched = availableProducts.find((product) => product.product_id === productId);
    setActiveModal((prev) => {
      if (!prev) return prev;
      const nextProducts = [...prev.products];
      nextProducts[index] = matched
        ? { ...matched }
        : { product_id: productId, name: '', current_stock: 0 };
      return { ...prev, products: nextProducts };
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => addSection({ width: 180, height: 65 })}
          className="inline-flex items-center gap-2 rounded-2xl bg-teal-700 px-4 py-3 text-sm font-bold text-white transition-colors hover:bg-teal-600"
        >
          <Plus size={16} />
          Add shelf (wide)
        </button>
        <button
          onClick={() => addSection({ width: 80, height: 140 })}
          className="inline-flex items-center gap-2 rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm font-bold text-stone-700 transition-colors hover:bg-white"
        >
          <Plus size={16} />
          Add shelf (tall)
        </button>
        <button
          onClick={() => addSection({ width: 100, height: 80 })}
          className="inline-flex items-center gap-2 rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm font-bold text-stone-700 transition-colors hover:bg-white"
        >
          <Plus size={16} />
          Add small cube
        </button>
      </div>

      <div
        ref={canvasRef}
        className="relative w-full overflow-hidden rounded-[28px] border border-black/5 shadow-[0_18px_45px_rgba(0,0,0,0.04)]"
        style={{
          height: `${CANVAS_HEIGHT}px`,
          backgroundColor: '#F7F6F2',
          backgroundImage: 'radial-gradient(circle, rgba(39, 80, 10, 0.12) 1px, transparent 1px)',
          backgroundSize: '18px 18px',
        }}
        onMouseMove={handleCanvasMouseMove}
        onMouseUp={handleCanvasMouseUp}
        onMouseLeave={handleCanvasMouseUp}
      >
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-stone-500">
            Loading store map...
          </div>
        )}

        {!loading && sections.map((section) => {
          const health = getHealthStyle(section);
          return (
            <div
              key={section.id}
              className="absolute cursor-move rounded-[22px] border-2 px-4 py-3 shadow-sm transition-shadow hover:shadow-md"
              style={{
                left: `${section.x}px`,
                top: `${section.y}px`,
                width: `${section.width}px`,
                height: `${section.height}px`,
                backgroundColor: health.background,
                borderColor: health.border,
                color: health.text,
              }}
              onMouseDown={(event) => beginPointerInteraction(event, section, 'drag')}
              onMouseEnter={() => setHoveredId(section.id)}
              onMouseLeave={() => setHoveredId((current) => (current === section.id ? null : current))}
              onClick={() => openModal(section)}
            >
              <div className="pointer-events-none">
                <div className="text-xs font-black uppercase tracking-[0.2em] opacity-70">Section</div>
                <div className="mt-1 text-lg font-black leading-tight">{section.name}</div>
                <div className="mt-2 text-xs font-semibold opacity-80">{section.products.length} product{section.products.length === 1 ? '' : 's'}</div>
              </div>

              {hoveredId === section.id && section.products.length > 0 && (
                <div
                  className="pointer-events-none absolute left-1/2 top-0 z-20 min-w-[220px] -translate-x-1/2 -translate-y-[110%] rounded-2xl border border-black/10 bg-white px-4 py-3 text-left text-stone-900 shadow-xl"
                >
                  <div className="mb-2 text-[10px] font-black uppercase tracking-[0.2em] text-stone-500">Live stock</div>
                  <div className="space-y-2">
                    {section.products.map((product) => (
                      <div key={`${section.id}-${product.product_id}`} className="flex items-center justify-between gap-3 text-sm">
                        <span className="font-semibold text-stone-800">{product.name}</span>
                        <span className="text-xs font-bold text-stone-500">{product.current_stock} units</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div
                className="absolute bottom-2 right-2 flex h-5 w-5 cursor-se-resize items-center justify-center rounded-md border border-black/10 bg-white/80 text-stone-500"
                onMouseDown={(event) => beginPointerInteraction(event, section, 'resize')}
                onClick={(event) => event.stopPropagation()}
              >
                <Grip size={12} />
              </div>
            </div>
          );
        })}
      </div>

      {activeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-[28px] border border-black/5 bg-[rgba(255,252,247,0.98)] p-6 shadow-[0_30px_100px_rgba(0,0,0,0.18)] lg:p-8">
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.22em] text-stone-500">Edit shelf section</div>
                <div className="mt-2 text-3xl font-bold tracking-tight text-stone-900">{activeModal.name || 'Shelf section'}</div>
              </div>
              <button
                type="button"
                onClick={closeModal}
                className="rounded-full border border-black/10 bg-white/80 p-2 text-stone-500 transition-colors hover:text-stone-900"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-5">
              <div>
                <div className="mb-2 text-xs font-black uppercase tracking-[0.18em] text-stone-500">Section Name</div>
                <input
                  type="text"
                  value={activeModal.name}
                  onChange={(event) => setActiveModal((prev) => ({ ...prev, name: event.target.value }))}
                  className="w-full rounded-2xl border border-black/10 bg-white/85 px-4 py-3 text-sm text-stone-900 focus:border-teal-600/50 focus:outline-none"
                />
              </div>

              <div>
                <div className="mb-3 text-xs font-black uppercase tracking-[0.18em] text-stone-500">Products</div>
                <div className="space-y-3">
                  {activeModal.products.map((product, index) => (
                    <div key={`${product.product_id}-${index}`} className="grid gap-3 rounded-2xl border border-black/8 bg-white/85 p-4 md:grid-cols-[minmax(0,1fr)_140px_48px] md:items-center">
                      <select
                        value={product.product_id}
                        onChange={(event) => updateModalProduct(index, event.target.value)}
                        className="w-full rounded-xl border border-black/10 bg-white px-3 py-2.5 text-sm text-stone-900 focus:border-teal-600/50 focus:outline-none"
                      >
                        {availableProducts.map((option) => (
                          <option key={option.product_id} value={option.product_id}>
                            {option.name}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        value={product.current_stock}
                        onChange={(event) => {
                          const nextValue = Number(event.target.value) || 0;
                          setActiveModal((prev) => {
                            if (!prev) return prev;
                            const nextProducts = [...prev.products];
                            nextProducts[index] = { ...nextProducts[index], current_stock: nextValue };
                            return { ...prev, products: nextProducts };
                          });
                        }}
                        className="w-full rounded-xl border border-black/10 bg-stone-50 px-3 py-2.5 text-sm text-stone-700"
                      />
                      <button
                        type="button"
                        onClick={() => setActiveModal((prev) => ({ ...prev, products: prev.products.filter((_, itemIndex) => itemIndex !== index) }))}
                        className="flex h-11 w-11 items-center justify-center rounded-xl border border-black/10 bg-white text-stone-500 transition-colors hover:bg-stone-100 hover:text-red-700"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const fallback = availableProducts[0];
                    if (!fallback) return;
                    setActiveModal((prev) => ({
                      ...prev,
                      products: [
                        ...prev.products,
                        {
                          product_id: fallback.product_id,
                          name: fallback.name,
                          current_stock: fallback.current_stock,
                        },
                      ],
                    }));
                  }}
                  className="mt-4 inline-flex items-center gap-2 rounded-2xl border border-black/10 bg-white px-4 py-3 text-sm font-bold text-stone-700 transition-colors hover:bg-stone-50"
                >
                  <Plus size={16} />
                  Add product
                </button>
              </div>
            </div>

            <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={deleteSection}
                className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 transition-colors hover:bg-red-100"
              >
                Delete
              </button>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-2xl px-4 py-3 text-sm font-bold text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-900"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveModal}
                  className="rounded-2xl bg-teal-700 px-5 py-3 text-sm font-bold text-white transition-colors hover:bg-teal-600"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
