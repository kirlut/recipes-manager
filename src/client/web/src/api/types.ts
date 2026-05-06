export type QuantityType = "weight" | "volume";

export interface UserRef {
  id: number;
  username: string;
  full_name: string | null;
}

export interface User extends UserRef {
  created_at: string;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: User;
}

export interface NutritionFactType {
  id: number;
  name: string;
  unit: string;
}

export interface ProductNutritionFact {
  nutrition_fact_id: number;
  nutrition_fact_name: string;
  unit: string;
  quantity_type: QuantityType;
  amount: number;
}

export interface ProductNutritionFactWrite {
  nutrition_fact_id: number;
  quantity_type: QuantityType;
  amount: number;
}

export interface ProductBase {
  id: number;
  name: string;
  image_filename: string | null;
  created_by: UserRef | null;
  import_source: string | null;
  created_at: string;
  starred_by_me: boolean;
}

export interface Product extends ProductBase {
  nutrition_facts: ProductNutritionFact[];
}

export interface ProductListItem extends ProductBase {}

export interface ProductWrite {
  name: string;
  image_filename: string | null;
  nutrition_facts: ProductNutritionFactWrite[];
}

export interface Page<T> {
  items: T[];
  self: string;
  next?: string;
}

export interface UploadResponse {
  filename: string;
}

export type ListScope = "mine" | "starred" | "search";

export interface ProblemViolation {
  field: string;
  message: string;
}

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  extensions?: {
    violations?: ProblemViolation[];
    [k: string]: unknown;
  };
}
