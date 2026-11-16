import { TestBed } from '@angular/core/testing';

import { Logar } from './logar';

describe('Logar', () => {
  let service: Logar;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(Logar);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
