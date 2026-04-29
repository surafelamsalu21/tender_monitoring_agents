import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: number;
  icon: LucideIcon;
  color: string;
  trend?: string;
}

export const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, color, trend }) => (
  <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8 hover:shadow-xl transition-all duration-300 hover:scale-105">
    <div className="flex items-center justify-between">
      <div className="flex-1">
        <p className="text-base font-medium text-gray-600 mb-2">{title}</p>
        <p className="text-4xl font-bold text-gray-900 mb-2">{value}</p>
        {trend && <p className="text-sm text-green-600 font-medium">{trend}</p>}
      </div>
      <div className={`p-4 rounded-xl ${color} shadow-lg`}>
        <Icon className="h-8 w-8 text-white" />
      </div>
    </div>
  </div>
);
