import { useMemo } from "react";
import * as THREE from "three";
import { Canvas } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import type { PainPoint } from "@/lib/types";

function buildHeartShape() {
  const shape = new THREE.Shape();
  const points: THREE.Vector2[] = [];
  const scale = 0.045;

  for (let i = 0; i <= 100; i += 1) {
    const t = (i / 100) * Math.PI * 2;
    const x = 16 * Math.pow(Math.sin(t), 3);
    const y =
      13 * Math.cos(t) -
      5 * Math.cos(2 * t) -
      2 * Math.cos(3 * t) -
      Math.cos(4 * t);
    points.push(new THREE.Vector2(x * scale, y * scale));
  }

  shape.setFromPoints(points);
  return shape;
}

function HeartMesh() {
  const heartShape = useMemo(buildHeartShape, []);
  const extrudeSettings = useMemo(
    () => ({
      depth: 0.35,
      bevelEnabled: true,
      bevelSegments: 3,
      steps: 1,
      bevelSize: 0.03,
      bevelThickness: 0.03,
    }),
    []
  );

  return (
    <mesh rotation={[Math.PI, 0, Math.PI]} position={[0, 0.2, 0]}>
      <extrudeGeometry args={[heartShape, extrudeSettings]} />
      <meshStandardMaterial color="#c80f3b" roughness={0.35} metalness={0.15} />
    </mesh>
  );
}

function PainMarkers({ painPoints }: { painPoints: PainPoint[] }) {
  return (
    <>
      {painPoints.map((point) => (
        <group key={`${point.symptom}-${point.x}-${point.y}-${point.z}`} position={[point.x, point.y, point.z]}>
          <mesh>
            <sphereGeometry args={[0.03, 24, 24]} />
            <meshStandardMaterial emissive="#ffd34d" emissiveIntensity={1.7} color="#ff9f00" />
          </mesh>
          <Html distanceFactor={8} position={[0.08, 0.08, 0]}>
            <div className="rounded bg-black/70 px-2 py-1 text-xs text-white">{point.label}</div>
          </Html>
        </group>
      ))}
    </>
  );
}

function RegionMarkers({
  regions,
}: {
  regions: {
    region: string;
    likelihood: "low" | "moderate" | "high";
    marker: { x: number; y: number; z: number };
  }[];
}) {
  return (
    <>
      {regions.map((entry) => (
        <group key={entry.region} position={[entry.marker.x, entry.marker.y, entry.marker.z]}>
          <mesh>
            <boxGeometry args={[0.04, 0.04, 0.04]} />
            <meshStandardMaterial color={entry.likelihood === "high" ? "#ef4444" : entry.likelihood === "moderate" ? "#f59e0b" : "#10b981"} />
          </mesh>
          <Html distanceFactor={8} position={[0.1, 0.1, 0]}>
            <div className="rounded bg-slate-900/80 px-2 py-1 text-xs text-white">{entry.region}</div>
          </Html>
        </group>
      ))}
    </>
  );
}

export function Heart3DModel({
  painPoints,
  regions = [],
}: {
  painPoints: PainPoint[];
  regions?: {
    region: string;
    likelihood: "low" | "moderate" | "high";
    marker: { x: number; y: number; z: number };
  }[];
}) {
  return (
    <div className="h-[380px] w-full rounded-xl border bg-gradient-to-b from-rose-50 via-slate-100 to-slate-200">
      <Canvas camera={{ position: [0, 0.55, 2.1], fov: 42 }}>
        <ambientLight intensity={0.85} />
        <directionalLight position={[1.4, 2.2, 1.3]} intensity={1.2} />
        <pointLight position={[-1.1, 0.8, 1.2]} intensity={0.7} />
        <HeartMesh />
        <PainMarkers painPoints={painPoints} />
        <RegionMarkers regions={regions} />
        <OrbitControls enablePan={false} minDistance={1.4} maxDistance={3} />
      </Canvas>
    </div>
  );
}
